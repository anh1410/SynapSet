from pydantic import BaseModel, Field, model_validator

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType


class BloomDistribution(BaseModel):
    """Target share of total marks per Bloom level. Values must sum to ~1.0."""

    weights: dict[BloomLevel, float]

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "BloomDistribution":
        total = sum(self.weights.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Bloom distribution weights must sum to 1.0, got {total}")
        return self


class PaperConstraints(BaseModel):
    total_marks: int
    bloom_distribution: BloomDistribution
    co_coverage: dict[str, int] = Field(
        default_factory=dict, description="Minimum number of questions required per CO id"
    )
    unit_marks: dict[int, int] = Field(
        default_factory=dict, description="Marks that must come from each unit"
    )
    num_questions: int | None = None
    allowed_question_types: list[QuestionType] | None = None
    max_overlap_with_recent_papers: float = Field(
        default=0.2, description="Max allowed fraction of questions reused from recent papers"
    )
