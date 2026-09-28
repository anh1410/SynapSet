"""Student-facing views of an Exam/Question — stripped of everything that
would let a student see the answer key (correct_answer, test_cases,
difficulty internals, password) before or during the attempt."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from app.schemas.submission import Submission


class PublicQuestion(BaseModel):
    id: str
    text: str
    question_type: QuestionType
    marks: int
    bloom_level: BloomLevel
    options: list[str] | None = None  # mcq/fill_in_blank choices (no correct_answer)
    code_language: str | None = None
    starter_code: str | None = None  # code_fix only (no test_cases/correct_answer)

    @classmethod
    def from_question(cls, q: Question) -> "PublicQuestion":
        return cls(
            id=q.id,
            text=q.text,
            question_type=q.question_type,
            marks=q.marks,
            bloom_level=q.bloom_level,
            options=q.options,
            code_language=q.code_language,
            starter_code=q.starter_code,
        )


class PublicExam(BaseModel):
    id: str
    name: str
    duration_minutes: int | None
    total_marks: int
    questions: list[PublicQuestion]
    timing: "ExamTiming | None" = None


class ExamTiming(BaseModel):
    """Everything a student client needs to show an exam's schedule. All times
    are server times (UTC); `server_time` lets a client correct for clock skew."""

    state: Literal["upcoming", "live", "closed"]
    closed_by: Literal["teacher", "schedule"] | None = None
    server_time: datetime
    go_live_at: datetime | None
    closes_at: datetime | None
    duration_minutes: int | None
    opens_in_seconds: int | None  # while upcoming
    closes_in_seconds: int | None  # while live and a closing time is set


class AttemptTiming(BaseModel):
    attempt_id: str
    started_at: datetime
    deadline: datetime | None  # start + duration, capped at the closing time; None = no limit
    remaining_seconds: int | None  # None = no limit
    expired: bool  # deadline (plus the short network grace) has passed
    submitted: bool
    submitted_at: datetime | None = None


class AttemptResponse(BaseModel):
    """Returned by start and by attempt status (reconnect)."""

    timing: ExamTiming
    attempt: AttemptTiming
    exam: PublicExam | None  # questions; omitted once the attempt is submitted or expired
    # Autosaved answers (question id -> answer) so a reconnecting client can restore its state.
    saved_answers: dict[str, str] = {}
    save_seq: int = 0
    last_saved_at: datetime | None = None


class SaveAnswersResult(BaseModel):
    saved_at: datetime | None
    save_seq: int
    applied: bool  # False = this save was older than one already applied (a replayed/out-of-order request)
    saved_count: int
    remaining_seconds: int | None
    deadline: datetime | None


class ReceiptAnswer(BaseModel):
    """Per-question status only: whether it was auto-graded or awaits the
    teacher. No marks, correctness, grading detail or answer key."""

    question_id: str
    status: Literal["auto_graded", "pending_review"]


class SubmissionReceipt(BaseModel):
    """What a student gets back from submitting: their auto-graded score and
    the marks still awaiting manual review (never counted as zero). The full
    graded Submission - per-question correctness, grading detail, question
    metadata snapshots - stays on the teacher's results API."""

    submission_id: str
    exam_id: str
    student_name: str
    student_identifier: str | None = None
    attempt_id: str | None = None
    auto_submitted: bool = False
    started_at: datetime | None = None
    submitted_at: datetime
    auto_graded_marks: int  # marks awarded on the auto-graded questions
    auto_graded_max_marks: int
    pending_review_marks: int  # max marks of answers awaiting the teacher
    pending_review_count: int
    total_max_marks: int
    answers: list[ReceiptAnswer]

    @classmethod
    def from_submission(cls, s: Submission) -> "SubmissionReceipt":
        graded = [a for a in s.answers if a.is_graded]
        pending = [a for a in s.answers if not a.is_graded]
        return cls(
            submission_id=s.id,
            exam_id=s.exam_id,
            student_name=s.student_name,
            student_identifier=s.student_identifier,
            attempt_id=s.attempt_id,
            auto_submitted=s.auto_submitted,
            started_at=s.started_at,
            submitted_at=s.submitted_at,
            auto_graded_marks=sum(a.marks_awarded for a in graded),
            auto_graded_max_marks=sum(a.max_marks for a in graded),
            pending_review_marks=sum(a.max_marks for a in pending),
            pending_review_count=len(pending),
            total_max_marks=s.total_max_marks,
            answers=[
                ReceiptAnswer(question_id=a.question_id, status="auto_graded" if a.is_graded else "pending_review")
                for a in s.answers
            ],
        )


PublicExam.model_rebuild()
