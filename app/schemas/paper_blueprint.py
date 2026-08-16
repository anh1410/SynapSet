from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

BlueprintStatus = Literal["draft", "exported"]


class PaperBlueprint(BaseModel):
    id: str
    name: str
    total_marks: int
    duration_minutes: int | None = None
    question_ids: list[str] = Field(default_factory=list)
    status: BlueprintStatus = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
