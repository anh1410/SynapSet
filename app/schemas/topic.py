from pydantic import BaseModel, Field


class Topic(BaseModel):
    id: str
    name: str
    description: str | None = None
    unit: int | None = None
    prerequisite_ids: list[str] = Field(default_factory=list)
    importance_score: float | None = None  # PageRank weight, set after graph scoring
    source_document: str | None = None
