"""Student-facing exam endpoints (no teacher auth; the exam password gates access).

Timed flow:  GET /timing -> POST /start (records the attempt's start on the
server) -> GET /attempts/{id} on refresh/reconnect -> POST /submit.
The start time is only ever taken from the server clock, and each student has
one attempt per exam, so restarting or reconnecting resumes the same timer.

Legacy flow (verify-password -> submit, no start) still works for exams with
no duration; exams with a duration require an attempt so the limit can be
enforced here rather than trusted to the client's timer.
"""

import math
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import clock
from app.core.attempt_store import get_attempt_store
from app.core.config import get_settings
from app.core.exam_store import get_exam_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.attempt import Attempt
from app.schemas.exam import Exam
from app.schemas.public_exam import AttemptResponse, AttemptTiming, ExamTiming, PublicExam, PublicQuestion
from app.schemas.question import Question
from app.schemas.submission import AnswerSubmission, GradedAnswer, Submission, student_key
from app.services.grading import AUTO_GRADABLE_TYPES, grade_answer

router = APIRouter(prefix="/api/v1/exams", tags=["submissions"])


def _published_exam_or_404(exam_id: str) -> Exam:
    """Any exam a student may know about: scheduled or closed, never a draft."""
    exam = get_exam_store().get(exam_id)
    if exam is None or exam.bucket == "draft":
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


def _live_exam_or_404(exam_id: str) -> Exam:
    exam = _published_exam_or_404(exam_id)
    if exam.bucket == "closed":
        raise HTTPException(status_code=403, detail="This exam is closed")
    if exam.bucket != "live":
        raise HTTPException(status_code=403, detail="This exam is not live yet")
    return exam


def _check_password(exam: Exam, password: str) -> None:
    if exam.password and password != exam.password:
        raise HTTPException(status_code=401, detail="Incorrect password")


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(0, math.ceil((moment - now).total_seconds()))


def _grace() -> timedelta:
    return timedelta(seconds=get_settings().submission_grace_seconds)


def exam_timing(exam: Exam) -> ExamTiming:
    now = clock.utcnow()
    bucket = exam.bucket
    state = "closed" if bucket == "closed" else "live" if bucket == "live" else "upcoming"
    return ExamTiming(
        state=state,
        closed_by=exam.closed_by,
        server_time=now,
        go_live_at=exam.go_live_at,
        closes_at=exam.closes_at,
        duration_minutes=exam.duration_minutes,
        opens_in_seconds=_seconds_until(exam.go_live_at, now) if state == "upcoming" and exam.go_live_at else None,
        closes_in_seconds=_seconds_until(exam.closes_at, now) if state == "live" and exam.closes_at else None,
    )


def _attempt_expired(attempt: Attempt, exam: Exam, now: datetime) -> bool:
    deadline = attempt.deadline(exam)
    return deadline is not None and now > deadline + _grace()


def attempt_timing(attempt: Attempt, exam: Exam) -> AttemptTiming:
    now = clock.utcnow()
    deadline = attempt.deadline(exam)
    return AttemptTiming(
        attempt_id=attempt.id,
        started_at=attempt.started_at,
        deadline=deadline,
        remaining_seconds=_seconds_until(deadline, now) if deadline else None,
        expired=_attempt_expired(attempt, exam, now),
        submitted=attempt.submitted_at is not None,
        submitted_at=attempt.submitted_at,
    )


def _public_exam(exam: Exam) -> PublicExam:
    bank = get_question_bank(exam.subject_id)
    questions = [q for qid in exam.question_ids if (q := bank.get(qid)) is not None]
    return PublicExam(
        id=exam.id,
        name=exam.name,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        questions=[PublicQuestion.from_question(q) for q in questions],
        timing=exam_timing(exam),
    )


def _attempt_response(attempt: Attempt, exam: Exam) -> AttemptResponse:
    timing = attempt_timing(attempt, exam)
    # Manual close ends every attempt; otherwise questions stay available until
    # the attempt is submitted or its own deadline passes.
    open_for_answers = not timing.submitted and not timing.expired and exam.status != "closed"
    return AttemptResponse(
        timing=exam_timing(exam),
        attempt=timing,
        exam=_public_exam(exam) if open_for_answers else None,
    )


def _metadata_snapshot(question: Question) -> dict:
    """Question metadata frozen onto the graded answer, so performance
    analytics survive later edits/deletions of the question."""
    return {
        "bloom_level": int(question.bloom_level),
        "topic_ids": list(question.topic_ids),
        "skill_category": question.effective_skill_category,
        "difficulty_score": question.difficulty_score,
    }


@router.get("/{exam_id}/timing", response_model=ExamTiming)
def get_timing(exam_id: str) -> ExamTiming:
    """Public schedule for an exam: whether it's upcoming/live/closed, when it
    opens and closes, and its duration. No password needed - it reveals no questions."""
    return exam_timing(_published_exam_or_404(exam_id))


class VerifyPasswordRequest(BaseModel):
    password: str = ""


@router.post("/{exam_id}/verify-password", response_model=PublicExam)
def verify_password(exam_id: str, request: VerifyPasswordRequest) -> PublicExam:
    """Checks the exam's access password and, if correct, hands back the
    student-safe question list (no answer keys). For timed exams, call /start
    instead so the attempt's start time is recorded."""
    exam = _live_exam_or_404(exam_id)
    _check_password(exam, request.password)
    return _public_exam(exam)


class StartAttemptRequest(BaseModel):
    password: str = ""
    student_name: str
    student_identifier: str | None = None


@router.post("/{exam_id}/start", response_model=AttemptResponse)
def start_attempt(exam_id: str, request: StartAttemptRequest) -> AttemptResponse:
    """Start - or resume - this student's attempt. The start time comes from
    the server clock. Calling it again (refresh, reconnect, another device)
    returns the same attempt with the time remaining, never a fresh timer."""
    exam = _published_exam_or_404(exam_id)
    _check_password(exam, request.password)
    if not request.student_name.strip():
        raise HTTPException(status_code=422, detail="Student name is required")

    store = get_attempt_store()
    key = student_key(request.student_name, request.student_identifier)
    existing = store.find(exam.id, key)
    if existing is not None:
        if existing.submitted_at is not None:
            raise HTTPException(status_code=409, detail="You have already submitted this exam")
        return _attempt_response(existing, exam)

    # New attempts only while the exam is live.
    _live_exam_or_404(exam_id)
    attempt = Attempt(
        id=str(uuid.uuid4()),
        exam_id=exam.id,
        student_key=key,
        student_name=request.student_name.strip(),
        student_identifier=(request.student_identifier or "").strip() or None,
        started_at=clock.utcnow(),
        duration_minutes=exam.duration_minutes,
    )
    store.add(attempt)
    return _attempt_response(attempt, exam)


@router.get("/{exam_id}/attempts/{attempt_id}", response_model=AttemptResponse)
def get_attempt(exam_id: str, attempt_id: str) -> AttemptResponse:
    """Attempt status for reconnecting clients: remaining time, expiry,
    submission state, and the questions while the attempt is still open.
    The attempt id is an unguessable token handed out by /start."""
    exam = _published_exam_or_404(exam_id)
    attempt = get_attempt_store().get(attempt_id)
    if attempt is None or attempt.exam_id != exam.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return _attempt_response(attempt, exam)


class SubmitExamRequest(BaseModel):
    password: str = ""
    student_name: str
    student_identifier: str | None = None
    attempt_id: str | None = None  # from /start; required for exams with a duration
    answers: list[AnswerSubmission]


def _resolve_attempt(exam: Exam, request: SubmitExamRequest) -> Attempt | None:
    store = get_attempt_store()
    if request.attempt_id:
        attempt = store.get(request.attempt_id)
        if attempt is None or attempt.exam_id != exam.id:
            raise HTTPException(status_code=404, detail="Attempt not found")
        return attempt
    return store.find(exam.id, student_key(request.student_name, request.student_identifier))


@router.post("/{exam_id}/submit", response_model=Submission)
def submit_exam(exam_id: str, request: SubmitExamRequest) -> Submission:
    """Grades every auto-gradable answer immediately (code_fix runs in the
    sandbox against hidden test cases; mcq/fill_in_blank/numerical are exact-
    matched) and stores the result for the teacher's dashboard. short_answer/
    long_answer questions are recorded ungraded, pending manual review.

    Refused once the attempt's deadline (start + duration, capped at the
    closing time) has passed by more than a short network grace, after the
    teacher closes the exam, and for a second submission of the same attempt."""
    exam = _published_exam_or_404(exam_id)
    if exam.status == "closed":
        raise HTTPException(status_code=403, detail="This exam is closed")
    if exam.bucket == "upcoming":
        raise HTTPException(status_code=403, detail="This exam is not live yet")
    _check_password(exam, request.password)

    now = clock.utcnow()
    attempt = _resolve_attempt(exam, request)
    if attempt is None:
        if exam.duration_minutes:
            raise HTTPException(status_code=409, detail="Start the exam before submitting")
        if exam.bucket == "closed":
            raise HTTPException(status_code=403, detail="This exam is closed")
        student_name, student_identifier, started_at = request.student_name, request.student_identifier, None
    else:
        if attempt.submitted_at is not None:
            raise HTTPException(status_code=409, detail="You have already submitted this exam")
        if _attempt_expired(attempt, exam, now):
            closed_first = exam.closes_at is not None and attempt.deadline(exam) == exam.closes_at
            detail = "This exam is closed" if closed_first else "Time is up - the exam duration has ended"
            raise HTTPException(status_code=403, detail=detail)
        student_name, student_identifier, started_at = attempt.student_name, attempt.student_identifier, attempt.started_at

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
        student_name=student_name,
        student_identifier=student_identifier,
        attempt_id=attempt.id if attempt else None,
        started_at=started_at,
        answers=graded,
        total_marks_awarded=0,
        total_max_marks=0,
        fully_auto_graded=False,
        submitted_at=now,
    )
    submission.recompute_totals()
    get_submission_store().add(submission)
    if attempt is not None:
        attempt.submitted_at = now
        attempt.submission_id = submission.id
        get_attempt_store().add(attempt)
    return submission
