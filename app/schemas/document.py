from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentCategory = Literal["syllabus", "notes", "papers"]
DocumentStatus = Literal["processing", "processed", "failed"]


class UploadedDocument(BaseModel):
    id: str
    filename: str
    category: DocumentCategory
    size_bytes: int
    status: DocumentStatus = "processing"
    topics_extracted: int = 0
    error_message: str | None = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
