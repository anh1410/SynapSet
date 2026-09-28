"""Student-facing views of an Exam/Question — stripped of everything that
would let a student see the answer key (correct_answer, test_cases,
difficulty internals, password) before or during the attempt."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType


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


PublicExam.model_rebuild()
