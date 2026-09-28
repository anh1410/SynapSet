import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from app.api.deps import get_current_teacher, require_subject
from app.core.attempt_store import get_attempt_store
from app.core.exam_store import get_exam_store
from app.core.pattern_store import get_pattern_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.exam import AssessmentType, Exam, ExamStatus
from app.schemas.question import Question
from app.schemas.submission import GradedAnswer, Submission
from app.schemas.teacher import Teacher
from app.api.submissions import attempt_timing
from app.schemas.public_exam import AttemptTiming
from app.services.exam_attempts import attempt_status, finalize_ended_attempts

router = APIRouter(prefix="/api/v1/exams", tags=["exams"], dependencies=[Depends(get_current_teacher)])


def _require_owner(exam_id: str, teacher: Teacher) -> Exam:
    exam = get_exam_store().get(exam_id)
    if exam is None or exam.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


def _validated_exam(data: dict) -> Exam:
    """Build an Exam through full validation (e.g. closing time after go-live),
    turning a model error into a 422 the teacher UI can show."""
    try:
        return Exam.model_validate(data)
    except ValidationError as exc:
        message = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        raise HTTPException(status_code=422, detail=message) from exc


def _check_pattern(pattern_id: str | None, subject_id: str, teacher: Teacher) -> None:
    if pattern_id is None:
        return
    pattern = get_pattern_store().get(pattern_id)
    if pattern is None or pattern.teacher_id != teacher.id or pattern.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Pattern not found")


class CreateExamRequest(BaseModel):
    subject_id: str
    name: str
    question_ids: list[str] = []
    total_marks: int = 0
    duration_minutes: int | None = None
    go_live_at: datetime | None = None
    closes_at: datetime | None = None
    exam_type: AssessmentType = "QUIZ"
    pattern_id: str | None = None


@router.post("", response_model=Exam)
def create_exam(request: CreateExamRequest, teacher: Teacher = Depends(get_current_teacher)) -> Exam:
    require_subject(request.subject_id, teacher)
    _check_pattern(request.pattern_id, request.subject_id, teacher)
    exam = _validated_exam(
        dict(
            id=str(uuid.uuid4()),
            teacher_id=teacher.id,
            subject_id=request.subject_id,
            name=request.name,
            question_ids=request.question_ids,
            total_marks=request.total_marks,
            duration_minutes=request.duration_minutes,
            go_live_at=request.go_live_at,
            closes_at=request.closes_at,
            status="scheduled" if request.go_live_at else "draft",
            exam_type=request.exam_type,
            pattern_id=request.pattern_id,
        )
    )
    get_exam_store().add(exam)
    return exam


@router.get("", response_model=list[Exam])
def list_exams(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[Exam]:
    require_subject(subject_id, teacher)
    return get_exam_store().list_by_subject(subject_id)


class ExamDetail(BaseModel):
    exam: Exam
    questions: list[Question]


@router.get("/{exam_id}", response_model=ExamDetail)
def get_exam(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> ExamDetail:
    exam = _require_owner(exam_id, teacher)
    bank = get_question_bank(exam.subject_id)
    questions = [q for qid in exam.question_ids if (q := bank.get(qid)) is not None]
    return ExamDetail(exam=exam, questions=questions)


class UpdateExamRequest(BaseModel):
    name: str | None = None
    question_ids: list[str] | None = None
    total_marks: int | None = None
    duration_minutes: int | None = None
    go_live_at: datetime | None = None
    closes_at: datetime | None = None
    password: str | None = None
    status: ExamStatus | None = None
    exam_type: AssessmentType | None = None
    pattern_id: str | None = None


@router.patch("/{exam_id}", response_model=Exam)
def update_exam(
    exam_id: str, request: UpdateExamRequest, teacher: Teacher = Depends(get_current_teacher)
) -> Exam:
    exam = _require_owner(exam_id, teacher)
    update_data = request.model_dump(exclude_unset=True)
    changes_paper = "question_ids" in update_data and update_data["question_ids"] != exam.question_ids
    if changes_paper and get_submission_store().list_by_exam(exam_id):
        raise HTTPException(
            status_code=409,
            detail="Students have already submitted this exam, so its questions can't be changed - results would no longer match the paper.",
        )
    if update_data.get("exam_type") is None:
        update_data.pop("exam_type", None)
    _check_pattern(update_data.get("pattern_id"), exam.subject_id, teacher)
    # Scheduling a go-live time without an explicit status moves a draft to "scheduled" -
    # otherwise the exam would silently stay stuck in the "draft" bucket forever.
    if "go_live_at" in update_data and update_data["go_live_at"] is not None and "status" not in update_data:
        update_data["status"] = "scheduled"
    updated = _validated_exam({**exam.model_dump(exclude={"bucket", "closed_by"}), **update_data})
    get_exam_store().add(updated)
    return updated


@router.delete("/{exam_id}")
def delete_exam(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> dict:
    _require_owner(exam_id, teacher)
    get_exam_store().remove(exam_id)
    return {"deleted": exam_id}


@router.get("/{exam_id}/submissions", response_model=list[Submission])
def list_submissions(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[Submission]:
    exam = _require_owner(exam_id, teacher)
    finalize_ended_attempts(exam)
    return get_submission_store().list_by_exam(exam_id)


class GradeAnswerRequest(BaseModel):
    marks_awarded: int
    feedback: str | None = None


@router.patch("/{exam_id}/submissions/{submission_id}/answers/{question_id}", response_model=Submission)
def grade_submission_answer(
    exam_id: str,
    submission_id: str,
    question_id: str,
    request: GradeAnswerRequest,
    teacher: Teacher = Depends(get_current_teacher),
) -> Submission:
    """Teacher grades (or re-grades) one answer by hand - how short_answer and
    long_answer questions get marks, and how an auto-grade can be overridden.
    Totals and the "needs review" flag are recomputed."""
    _require_owner(exam_id, teacher)
    store = get_submission_store()
    submission = store.get(submission_id)
    if submission is None or submission.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="Submission not found")
    answer: GradedAnswer | None = next((a for a in submission.answers if a.question_id == question_id), None)
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer not found in this submission")
    if not 0 <= request.marks_awarded <= answer.max_marks:
        raise HTTPException(status_code=422, detail=f"Marks must be between 0 and {answer.max_marks}")

    answer.marks_awarded = request.marks_awarded
    answer.manually_graded = True
    answer.feedback = request.feedback
    if request.marks_awarded == answer.max_marks:
        answer.correct = True
    elif request.marks_awarded == 0:
        answer.correct = False
    else:
        answer.correct = None  # partial credit
    answer.detail = f"Graded by teacher: {request.marks_awarded}/{answer.max_marks}"
    submission.recompute_totals()
    store.add(submission)
    return submission


class AttemptSummary(AttemptTiming):
    student_name: str
    student_identifier: str | None = None
    status: str  # in_progress | submitted | timed_out | closed
    saved_answer_count: int
    last_saved_at: datetime | None = None


@router.get("/{exam_id}/attempts", response_model=list[AttemptSummary])
def list_attempts(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[AttemptSummary]:
    """Who has started this exam, and whether each attempt is in progress,
    submitted, or ran out of time."""
    exam = _require_owner(exam_id, teacher)
    finalize_ended_attempts(exam)
    return [
        AttemptSummary(
            **attempt_timing(a, exam).model_dump(),
            student_name=a.student_name,
            student_identifier=a.student_identifier,
            status=attempt_status(a, exam),
            saved_answer_count=len(a.saved_answers),
            last_saved_at=a.last_saved_at,
        )
        for a in get_attempt_store().list_by_exam(exam_id)
    ]
