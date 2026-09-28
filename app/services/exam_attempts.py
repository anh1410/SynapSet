"""Grading/recording a student's answers and the attempt lifecycle around it.

Shared by the student endpoints (submit, autosave) and by lazy finalisation:
an attempt whose time ran out - or whose exam the teacher closed - while it
still had autosaved answers is turned into a submission from those answers
(marked auto_submitted), so a student's saved work is never silently lost.
Finalisation runs whenever an exam's attempts or submissions are read, so
no background scheduler is needed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.core import clock
from app.core.attempt_store import get_attempt_store
from app.core.config import get_settings
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.attempt import Attempt
from app.schemas.exam import Exam
from app.schemas.question import Question
from app.schemas.submission import GradedAnswer, Submission
from app.services.grading import AUTO_GRADABLE_TYPES, grade_answer

AttemptStatus = Literal["in_progress", "submitted", "timed_out", "closed"]


AUTO_SUBMITTED_DETAIL = "Time is up - your saved answers were submitted automatically when the exam ended."


def grace() -> timedelta:
    return timedelta(seconds=get_settings().submission_grace_seconds)


def attempt_expired(attempt: Attempt, exam: Exam, now: datetime) -> bool:
    deadline = attempt.deadline(exam)
    return deadline is not None and now > deadline + grace()


def attempt_status(attempt: Attempt, exam: Exam, now: datetime | None = None) -> AttemptStatus:
    now = now or clock.utcnow()
    if attempt.submitted_at is not None:
        return "submitted"
    if exam.status == "closed":
        return "closed"
    return "timed_out" if attempt_expired(attempt, exam, now) else "in_progress"


@dataclass
class AttemptState:
    """Lightweight (exam_id, status) pair for analytics."""

    exam_id: str
    status: AttemptStatus


def _metadata_snapshot(question: Question) -> dict:
    """Question metadata frozen onto the graded answer, so performance
    analytics survive later edits/deletions of the question."""
    return {
        "bloom_level": int(question.bloom_level),
        "topic_ids": list(question.topic_ids),
        "skill_category": question.effective_skill_category,
        "difficulty_score": question.difficulty_score,
    }


def grade_and_record(
    exam: Exam,
    answers_by_qid: dict[str, str],
    student_name: str,
    student_identifier: str | None,
    attempt: Attempt | None,
    submitted_at: datetime,
    auto_submitted: bool = False,
) -> Submission:
    """Grade every auto-gradable answer (code_fix in the sandbox against hidden
    test cases; mcq/fill_in_blank/numerical exact-matched), record the
    submission, and close the attempt. short/long answers await manual grading."""
    bank = get_question_bank(exam.subject_id)
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
        exam_id=exam.id,
        student_name=student_name,
        student_identifier=student_identifier,
        attempt_id=attempt.id if attempt else None,
        auto_submitted=auto_submitted,
        started_at=attempt.started_at if attempt else None,
        answers=graded,
        total_marks_awarded=0,
        total_max_marks=0,
        fully_auto_graded=False,
        submitted_at=submitted_at,
    )
    submission.recompute_totals()
    get_submission_store().add(submission)
    if attempt is not None:
        attempt.submitted_at = submitted_at
        attempt.submission_id = submission.id
        attempt.auto_submitted = auto_submitted
        get_attempt_store().add(attempt)
    return submission


def finalize_ended_attempts(exam: Exam) -> list[Submission]:
    """Submit, from their autosaved answers, attempts that can no longer be
    submitted by the student: time ran out, or the teacher closed the exam.
    Attempts with nothing saved are left as-is (the student never answered)."""
    now = clock.utcnow()
    finalized = []
    for attempt in get_attempt_store().list_by_exam(exam.id):
        if attempt.submitted_at is not None or not attempt.saved_answers:
            continue
        status = attempt_status(attempt, exam, now)
        if status not in ("timed_out", "closed"):
            continue
        # Stamp it at the moment it actually ended, not whenever it was noticed.
        deadline = attempt.deadline(exam)
        ended_at = min(deadline, now) if deadline is not None else now
        if attempt.last_saved_at is not None:
            ended_at = max(ended_at, attempt.last_saved_at)
        finalized.append(
            grade_and_record(
                exam,
                attempt.saved_answers,
                attempt.student_name,
                attempt.student_identifier,
                attempt,
                ended_at,
                auto_submitted=True,
            )
        )
    return finalized
