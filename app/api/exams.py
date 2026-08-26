import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_teacher, require_subject
from app.core.exam_store import get_exam_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.exam import Exam, ExamStatus
from app.schemas.question import Question
from app.schemas.submission import Submission
from app.schemas.teacher import Teacher

router = APIRouter(prefix="/api/v1/exams", tags=["exams"], dependencies=[Depends(get_current_teacher)])


def _require_owner(exam_id: str, teacher: Teacher) -> Exam:
    exam = get_exam_store().get(exam_id)
    if exam is None or exam.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


class CreateExamRequest(BaseModel):
    subject_id: str
    name: str
    question_ids: list[str] = []
    total_marks: int = 0
    duration_minutes: int | None = None


@router.post("", response_model=Exam)
def create_exam(request: CreateExamRequest, teacher: Teacher = Depends(get_current_teacher)) -> Exam:
    require_subject(request.subject_id, teacher)
    exam = Exam(
        id=str(uuid.uuid4()),
        teacher_id=teacher.id,
        subject_id=request.subject_id,
        name=request.name,
        question_ids=request.question_ids,
        total_marks=request.total_marks,
        duration_minutes=request.duration_minutes,
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
    password: str | None = None
    status: ExamStatus | None = None


@router.patch("/{exam_id}", response_model=Exam)
def update_exam(
    exam_id: str, request: UpdateExamRequest, teacher: Teacher = Depends(get_current_teacher)
) -> Exam:
    exam = _require_owner(exam_id, teacher)
    update_data = request.model_dump(exclude_unset=True)
    # Scheduling a go-live time without an explicit status moves a draft to "scheduled" -
    # otherwise the exam would silently stay stuck in the "draft" bucket forever.
    if "go_live_at" in update_data and update_data["go_live_at"] is not None and "status" not in update_data:
        update_data["status"] = "scheduled"
    updated = exam.model_copy(update=update_data)
    get_exam_store().add(updated)
    return updated


@router.delete("/{exam_id}")
def delete_exam(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> dict:
    _require_owner(exam_id, teacher)
    get_exam_store().remove(exam_id)
    return {"deleted": exam_id}


@router.get("/{exam_id}/submissions", response_model=list[Submission])
def list_submissions(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[Submission]:
    _require_owner(exam_id, teacher)
    return get_submission_store().list_by_exam(exam_id)
