from pydantic import BaseModel

from app.schemas.bloom import BloomLevel


class CourseOutcome(BaseModel):
    id: str
    code: str  # e.g. "CO1"
    description: str
    target_bloom_level: BloomLevel | None = None
