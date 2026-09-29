from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Subject(BaseModel):
    id: str
    teacher_id: str
    name: str
    # Code students enter on their dashboard to join this subject. Generated
    # on creation (or lazily for older subjects); the teacher can rotate it.
    join_code: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
