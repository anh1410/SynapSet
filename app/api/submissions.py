import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.exam_store import get_exam_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.public_exam import PublicExam, PublicQuestion
from app.schemas.question import Question
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


def _metadata_snapshot(question: Question) -> dict:
    """Question metadata frozen onto the graded answer, so performance
    analytics survive later edits/deletions of the question."""
    return {
        "bloom_level": int(question.bloom_level),
        "topic_ids": list(question.topic_ids),
        "skill_category": question.effective_skill_category,
        "difficulty_score": question.difficulty_score,
    }


class VerifyPasswordRequest(BaseModel):
    password: str = ""


@router.post("/{exam_id}/verify-password", response_model=PublicExam)
def verify_password(exam_id: str, request: VerifyPasswordRequest) -> PublicExam:
    """Checks the exam's access password and, if correct, hands back the
    student-safe question list (no answer keys) to start the attempt."""
    exam = _live_exam_or_404(exam_id)
    if exam.password and request.password != exam.password:
        raise HTTPException(status_code=401, detail="Incorrect password")

    bank = get_question_bank(exam.subject_id)
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

    bank = get_question_bank(exam.subject_id)
    answers_by_qid = {a.question_id: a.answer for a in request.answers}

    graded: list[GradedAnswer] = []
    for qid in exam.question_ids:
        question = bank.get(qid)
        if question is None:
            continue
        answer = answers_by_qid.get(qid, "")
        if question.question_type in AUTO_GRADABLE_TYPES:
            result = grade_answer(question, answer)
            tests = result.test_results
            graded.append(
                GradedAnswer(
                    question_id=qid,
                    question_type=question.question_type,
                    auto_graded=True,
                    correct=result.correct,
                    marks_awarded=result.marks_awarded,
                    max_marks=result.max_marks,
                    detail=result.detail,
                    answer=answer,
                    test_cases_passed=sum(1 for t in tests if t.passed) if tests is not None else None,
                    test_cases_total=len(tests) if tests is not None else None,
                    **_metadata_snapshot(question),
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
                    answer=answer,
                    **_metadata_snapshot(question),
                )
            )

    submission = Submission(
        id=str(uuid.uuid4()),
        exam_id=exam_id,
        student_name=request.student_name,
        student_identifier=request.student_identifier,
        answers=graded,
        total_marks_awarded=0,
        total_max_marks=0,
        fully_auto_graded=False,
        submitted_at=datetime.now(UTC),
    )
    submission.recompute_totals()
    get_submission_store().add(submission)
    return submission
