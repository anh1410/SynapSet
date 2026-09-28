from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.bloom import BloomLevel
from app.schemas.skill import SkillCategory, resolve_skill_category


class QuestionType(str, Enum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    NUMERICAL = "numerical"
    FILL_IN_BLANK = "fill_in_blank"  # blank-style stem, graded like MCQ via options/correct_answer
    CODE_FIX = "code_fix"  # correct the code / find the mistake / fill the missing line


class CodeTestCase(BaseModel):
    """One hidden input/expected-output pair used to auto-grade a code_fix answer."""

    input: str = ""
    expected_output: str


class Question(BaseModel):
    id: str
    text: str
    question_type: QuestionType
    marks: int
    bloom_level: BloomLevel
    topic_ids: list[str] = Field(default_factory=list)
    co_ids: list[str] = Field(default_factory=list)
    unit: int | None = None

    options: list[str] | None = None  # MCQ / fill_in_blank choices
    correct_answer: str | None = None  # MCQ/fill_in_blank correct option, or reference-corrected code for code_fix

    code_language: str | None = None  # code_fix only, e.g. "python"
    starter_code: str | None = None  # code_fix only: the buggy/incomplete code shown to the student
    test_cases: list[CodeTestCase] | None = None  # code_fix only: hidden cases used to auto-grade submissions

    difficulty_score: float | None = None  # 1-10, set by difficulty scorer (Phase 5)
    embedding_id: str | None = None  # reference into the vector store
    is_duplicate_of: str | None = None  # id of the original question, if flagged

    # Optional teacher override; when unset the category is derived from
    # question_type + bloom_level (see app.schemas.skill).
    skill_category: SkillCategory | None = None

    source_document: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def effective_skill_category(self) -> SkillCategory:
        return resolve_skill_category(self.question_type.value, int(self.bloom_level), self.skill_category)
