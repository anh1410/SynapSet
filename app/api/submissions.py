"""Student-facing exam endpoints (no teacher auth; the exam password gates access).

Timed flow:  GET /timing -> POST /start (records the attempt's start on the
server) -> PUT /attempts/{id}/answers (autosave, repeatedly) -> GET
/attempts/{id} on refresh/reconnect (restores saved answers) -> POST /submit.
The start time is only ever taken from the server clock, and each student has
one attempt per exam, so restarting or reconnecting resumes the same timer.
If time runs out (or the teacher closes the exam) before the student submits,
the attempt is finalised from its autosaved answers.

Legacy flow (verify-password -> submit, no start) still works for exams with
no duration; exams with a duration require an attempt so the limit can be
enforced here rather than trusted to the client's timer.
"""

import math
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import clock
from app.core.attempt_store import get_attempt_store
from app.core.exam_store import get_exam_store
from app.core.question_bank import get_question_bank
from app.schemas.attempt import Attempt
from app.schemas.exam import Exam
from app.schemas.public_exam import (
    AttemptResponse,
    AttemptTiming,
    ExamTiming,
    PublicExam,
    PublicQuestion,
    SaveAnswersResult,
    SubmissionReceipt,
)
from app.schemas.submission import AnswerSubmission, student_key
from app.services.exam_attempts import AUTO_SUBMITTED_DETAIL, attempt_expired, finalize_ended_attempts, grade_and_record

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


def attempt_timing(attempt: Attempt, exam: Exam) -> AttemptTiming:
    now = clock.utcnow()
    deadline = attempt.deadline(exam)
    return AttemptTiming(
        attempt_id=attempt.id,
        started_at=attempt.started_at,
        deadline=deadline,
        remaining_seconds=_seconds_until(deadline, now) if deadline else None,
        expired=attempt_expired(attempt, exam, now),
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
        saved_answers=attempt.saved_answers,
        save_seq=attempt.save_seq,
        last_saved_at=attempt.last_saved_at,
    )


def _reload(attempt: Attempt) -> Attempt:
    return get_attempt_store().get(attempt.id) or attempt


def _refuse_finished(attempt: Attempt) -> None:
    """A submitted attempt can't be resumed, saved or submitted again. Tell the
    student whether *they* submitted, or the server did when time ran out."""
    if attempt.submitted_at is None:
        return
    if attempt.auto_submitted:
        raise HTTPException(status_code=403, detail=AUTO_SUBMITTED_DETAIL)
    raise HTTPException(status_code=409, detail="You have already submitted this exam")


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
    returns the same attempt with the time remaining and the autosaved
    answers, never a fresh timer."""
    exam = _published_exam_or_404(exam_id)
    _check_password(exam, request.password)
    if not request.student_name.strip():
        raise HTTPException(status_code=422, detail="Student name is required")
    finalize_ended_attempts(exam)

    store = get_attempt_store()
    key = student_key(request.student_name, request.student_identifier)
    existing = store.find(exam.id, key)
    if existing is not None:
        _refuse_finished(existing)
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


def _attempt_or_404(exam: Exam, attempt_id: str) -> Attempt:
    attempt = get_attempt_store().get(attempt_id)
    if attempt is None or attempt.exam_id != exam.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt


@router.get("/{exam_id}/attempts/{attempt_id}", response_model=AttemptResponse)
def get_attempt(exam_id: str, attempt_id: str) -> AttemptResponse:
    """Attempt status for reconnecting clients: remaining time, expiry,
    submission state, autosaved answers, and the questions while the attempt
    is still open. The attempt id is an unguessable token handed out by /start."""
    exam = _published_exam_or_404(exam_id)
    attempt = _attempt_or_404(exam, attempt_id)
    finalize_ended_attempts(exam)
    return _attempt_response(_reload(attempt), exam)


class SaveAnswersRequest(BaseModel):
    answers: list[AnswerSubmission]  # changed answers; merged into what's already saved
    # Client-side counter, incremented on every save. A save with a sequence
    # number at or below one already applied (a retry that arrives late after a
    # reconnect) is ignored so it can't overwrite newer answers.
    seq: int | None = None


@router.put("/{exam_id}/attempts/{attempt_id}/answers", response_model=SaveAnswersResult)
def save_answers(exam_id: str, attempt_id: str, request: SaveAnswersRequest) -> SaveAnswersResult:
    """Autosave. Refused once the attempt is submitted, its deadline (plus the
    network grace) has passed, or the teacher has closed the exam - saving
    never extends the deadline."""
    exam = _published_exam_or_404(exam_id)
    attempt = _attempt_or_404(exam, attempt_id)
    now = clock.utcnow()
    _refuse_finished(attempt)
    if exam.status == "closed":
        finalize_ended_attempts(exam)
        raise HTTPException(status_code=403, detail="This exam is closed")
    if attempt_expired(attempt, exam, now):
        finalize_ended_attempts(exam)
        raise HTTPException(status_code=403, detail="Time is up - answers can no longer be saved")

    timing = attempt_timing(attempt, exam)
    if request.seq is not None and request.seq <= attempt.save_seq:
        return SaveAnswersResult(
            saved_at=attempt.last_saved_at, save_seq=attempt.save_seq, applied=False,
            saved_count=len(attempt.saved_answers), remaining_seconds=timing.remaining_seconds, deadline=timing.deadline,
        )

    valid_ids = set(exam.question_ids)
    for a in request.answers:
        if a.question_id in valid_ids:
            attempt.saved_answers[a.question_id] = a.answer
    attempt.save_seq = request.seq if request.seq is not None else attempt.save_seq + 1
    attempt.last_saved_at = now
    get_attempt_store().add(attempt)
    return SaveAnswersResult(
        saved_at=now, save_seq=attempt.save_seq, applied=True, saved_count=len(attempt.saved_answers),
        remaining_seconds=timing.remaining_seconds, deadline=timing.deadline,
    )


class SubmitExamRequest(BaseModel):
    password: str = ""
    student_name: str
    student_identifier: str | None = None
    attempt_id: str | None = None  # from /start; required for exams with a duration
    answers: list[AnswerSubmission]


def _resolve_attempt(exam: Exam, request: SubmitExamRequest) -> Attempt | None:
    if request.attempt_id:
        return _attempt_or_404(exam, request.attempt_id)
    return get_attempt_store().find(exam.id, student_key(request.student_name, request.student_identifier))


@router.post("/{exam_id}/submit", response_model=SubmissionReceipt)
def submit_exam(exam_id: str, request: SubmitExamRequest) -> SubmissionReceipt:
    """Grades and records the attempt. The final answers are the autosaved
    ones overlaid with anything sent in this request (the newest state).
    The student gets a trimmed receipt (auto-graded score + marks pending
    review); the full graded submission stays on the teacher's results API.

    Refused once the attempt's deadline (start + duration, capped at the
    closing time) has passed by more than a short network grace, after the
    teacher closes the exam, and for a second submission of the same attempt.
    (A refused late attempt is still finalised from its autosaved answers.)"""
    exam = _published_exam_or_404(exam_id)
    if exam.status == "closed":
        finalize_ended_attempts(exam)
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
        answers = {a.question_id: a.answer for a in request.answers}
        return SubmissionReceipt.from_submission(
            grade_and_record(exam, answers, request.student_name, request.student_identifier, None, now)
        )

    _refuse_finished(attempt)
    if attempt_expired(attempt, exam, now):
        finalize_ended_attempts(exam)
        if _reload(attempt).auto_submitted:
            raise HTTPException(status_code=403, detail=AUTO_SUBMITTED_DETAIL)
        closed_first = exam.closes_at is not None and attempt.deadline(exam) == exam.closes_at
        detail = "This exam is closed" if closed_first else "Time is up - the exam duration has ended"
        raise HTTPException(status_code=403, detail=detail)

    answers = {**attempt.saved_answers, **{a.question_id: a.answer for a in request.answers}}
    return SubmissionReceipt.from_submission(
        grade_and_record(exam, answers, attempt.student_name, attempt.student_identifier, attempt, now)
    )
