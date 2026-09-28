from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.core import clock

ExamStatus = Literal["draft", "scheduled", "closed"]
ExamBucket = Literal["draft", "upcoming", "live", "closed"]
# QUIZ = the original free-form weekly quiz; MSE/SEE = built against an exam pattern.
AssessmentType = Literal["QUIZ", "MSE", "SEE"]
ClosedBy = Literal["teacher", "schedule"]


class Exam(BaseModel):
    id: str
    teacher_id: str
    subject_id: str
    name: str
    question_ids: list[str] = Field(default_factory=list)
    total_marks: int = 0
    duration_minutes: int | None = None
    go_live_at: datetime | None = None
    # Optional automatic closing time; after it the exam is closed to new
    # attempts and submissions (students mid-attempt get their deadline capped to it).
    closes_at: datetime | None = None
    password: str | None = None
    status: ExamStatus = "draft"
    exam_type: AssessmentType = "QUIZ"
    pattern_id: str | None = None  # the ExamPattern this exam was assembled against, if any
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("go_live_at", "closes_at")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        # A naive timestamp can't be compared with the server clock; treat it as UTC.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @model_validator(mode="after")
    def _closes_after_go_live(self):
        if self.go_live_at and self.closes_at and self.closes_at <= self.go_live_at:
            raise ValueError("Closing time must be after the go-live time")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bucket(self) -> ExamBucket:
        """Display bucket for the Exams inventory: draft (still being built),
        upcoming (scheduled, hasn't gone live), live (go-live time has passed,
        still open), or closed (teacher closed it manually, or its closing
        time has passed)."""
        if self.status == "closed":
            return "closed"
        if self.status == "draft" or self.go_live_at is None:
            return "draft"
        now = clock.utcnow()
        if self.closes_at is not None and now >= self.closes_at:
            return "closed"
        return "live" if self.go_live_at <= now else "upcoming"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def closed_by(self) -> ClosedBy | None:
        """Why a closed exam is closed: the teacher pressed Close, or its closing time passed."""
        if self.status == "closed":
            return "teacher"
        return "schedule" if self.bucket == "closed" else None
