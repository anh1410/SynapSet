from typing import Literal

from pydantic import BaseModel


class DifficultyScore(BaseModel):
    score: float  # 1-10
    features: dict[str, float]
    shap_contributions: dict[str, float] | None = None
    method: Literal["heuristic", "model"]
