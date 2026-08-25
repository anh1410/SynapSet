import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.exam_store import get_exam_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.public_exam import PublicExam, PublicQuestion
from app.schemas.submission import AnswerSubmission, GradedAnswer, Submission
from app.services.grading import AUTO_GRADABLE_TYPES, grade_answer

router = APIRouter(prefix="/api/v1/exams", tags=["submissions"])


def _live_exam_or_404(exam_id: str):
    exam = get_exam_store().get(exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.bucket == "closed":
        raise HTTPException(status_code=403, detail="This exam is closed")
    if exam.bucket != "live":
        raise HTTPException(status_code=403, detail="This exam is not live yet")
    return exam


class VerifyPasswordRequest(BaseModel):
    password: str = ""


@router.post("/{exam_id}/verify-password", response_model=PublicExam)
def verify_password(exam_id: str, request: VerifyPasswordRequest) -> PublicExam:
    """Checks the exam's access password and, if correct, hands back the
    student-safe question list (no answer keys) to start the attempt."""
    exam = _live_exam_or_404(exam_id)
    if exam.password and request.password != exam.password:
        raise HTTPException(status_code=401, detail="Incorrect password")

    bank = get_question_bank()
    questions = [q for qid in exam.question_ids if (q := bank.get(qid)) is not None]
    return PublicExam(
        id=exam.id,
        name=exam.name,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        questions=[PublicQuestion.from_question(q) for q in questions],
    )


class SubmitExamRequest(BaseModel):
    password: str = ""
    student_name: str
    student_identifier: str | None = None
    answers: list[AnswerSubmission]


@router.post("/{exam_id}/submit", response_model=Submission)
def submit_exam(exam_id: str, request: SubmitExamRequest) -> Submission:
    """Grades every auto-gradable answer immediately (code_fix runs in the
    sandbox against hidden test cases; mcq/fill_in_blank/numerical are exact-
    matched) and stores the result for the teacher's dashboard. short_answer/
    long_answer questions are recorded ungraded, pending manual review."""
    exam = _live_exam_or_404(exam_id)
    if exam.password and request.password != exam.password:
        raise HTTPException(status_code=401, detail="Incorrect password")

    bank = get_question_bank()
    answers_by_qid = {a.question_id: a.answer for a in request.answers}

    graded: list[GradedAnswer] = []
    for qid in exam.question_ids:
        question = bank.get(qid)
        if question is None:
            continue
        answer = answers_by_qid.get(qid, "")
        if question.question_type in AUTO_GRADABLE_TYPES:
            result = grade_answer(question, answer)
            graded.append(
                GradedAnswer(
                    question_id=qid,
                    question_type=question.question_type,
                    auto_graded=True,
                    correct=result.correct,
                    marks_awarded=result.marks_awarded,
                    max_marks=result.max_marks,
                    detail=result.detail,
                )
            )
        else:
            graded.append(
                GradedAnswer(
                    question_id=qid,
                    question_type=question.question_type,
                    auto_graded=False,
                    correct=None,
                    marks_awarded=0,
                    max_marks=question.marks,
                    detail="Needs manual grading",
                )
            )

    submission = Submission(
        id=str(uuid.uuid4()),
        exam_id=exam_id,
        student_name=request.student_name,
        student_identifier=request.student_identifier,
        answers=graded,
        total_marks_awarded=sum(g.marks_awarded for g in graded),
        total_max_marks=sum(g.max_marks for g in graded),
        fully_auto_graded=all(g.auto_graded for g in graded),
        submitted_at=datetime.now(UTC),
    )
    get_submission_store().add(submission)
    return submission
