"""Skill categories used to split performance into conceptual understanding,
reasoning/analytical ability, and coding skill.

A question's category is *derived* from metadata every question already has
(question_type + Bloom's level), so existing questions and submissions are
analysable without a migration. A teacher can still pin a category on an
individual question via Question.skill_category when the default rule gets it
wrong (e.g. a Remember-level numerical that is really a reasoning problem).
"""

from enum import Enum
from typing import Literal

from app.schemas.bloom import BloomLevel


class SkillCategory(str, Enum):
    CONCEPTUAL = "conceptual"  # recall / understanding of concepts (Bloom's Remember, Understand)
    REASONING = "reasoning"  # applying / analysing / evaluating / creating (Bloom's Apply and above)
    CODING = "coding"  # writing, fixing, or completing programs


DifficultyBucket = Literal["easy", "medium", "hard"]

# Bloom's levels at or above this count as higher-order (reasoning) questions.
REASONING_MIN_BLOOM = BloomLevel.APPLY


def resolve_skill_category(
    question_type: str, bloom_level: int, override: "SkillCategory | str | None" = None
) -> SkillCategory:
    if override:
        return SkillCategory(override)
    if question_type in ("code_fix", "code_write"):
        return SkillCategory.CODING
    if bloom_level >= REASONING_MIN_BLOOM:
        return SkillCategory.REASONING
    return SkillCategory.CONCEPTUAL


def difficulty_bucket(score: float | None) -> DifficultyBucket:
    """Same thresholds the frontend uses (src/lib/api.ts difficultyBucket), so
    "Hard" means the same thing in the bank, the pattern, and the analytics.
    Unscored questions count as medium, matching the frontend."""
    if score is None:
        return "medium"
    if score <= 4:
        return "easy"
    if score <= 7:
        return "medium"
    return "hard"
