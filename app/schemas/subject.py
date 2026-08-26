from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Subject(BaseModel):
    id: str
    teacher_id: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
