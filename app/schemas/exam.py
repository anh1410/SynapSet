from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

ExamStatus = Literal["draft", "scheduled", "closed"]
ExamBucket = Literal["draft", "upcoming", "live", "closed"]


class Exam(BaseModel):
    id: str
    teacher_id: str
    subject_id: str
    name: str
    question_ids: list[str] = Field(default_factory=list)
    total_marks: int = 0
    duration_minutes: int | None = None
    go_live_at: datetime | None = None
    password: str | None = None
    status: ExamStatus = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bucket(self) -> ExamBucket:
        """Display bucket for the Exams inventory: draft (still being built),
        upcoming (scheduled, hasn't gone live), live (go-live time has passed,
        still open), or closed (teacher manually closed it to submissions)."""
        if self.status == "closed":
            return "closed"
        if self.status == "draft" or self.go_live_at is None:
            return "draft"
        return "live" if self.go_live_at <= datetime.now(UTC) else "upcoming"
