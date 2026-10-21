from datetime import UTC, datetime
from enum import Enum
from typing import Literal

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
    CODE_WRITE = "code_write"  # write the whole program (from scratch, or an interview-style scenario)


# Programming questions: answered with code, auto-graded by running it against hidden test cases.
CODING_TYPES = frozenset({QuestionType.CODE_FIX, QuestionType.CODE_WRITE})


class CodeTestCase(BaseModel):
    """One hidden input/expected-output pair used to auto-grade a coding answer."""

    input: str = ""
    expected_output: str


class SourceChunk(BaseModel):
    """A course-material passage the generator was grounded on."""

    source_document: str | None = None
    chunk_index: int | None = None
    excerpt: str
    relevance: float | None = None  # 1 - cosine distance from the retrieval query


class QuestionProvenance(BaseModel):
    """Recorded at generation time so a generated question is traceable: which
    topic it was asked for, which passages were retrieved as grounding, and
    which knowledge-graph relations were given to the model."""

    requested_topic: str
    retrieved_chunks: list[SourceChunk] = Field(default_factory=list)
    graph_relations: list[str] = Field(default_factory=list)  # e.g. "Stacks --[PREREQUISITE_OF]--> Recursion"
    model: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    correct_answer: str | None = None  # MCQ/fill_in_blank correct option, or the reference solution for coding types

    code_language: str | None = None  # coding types only, e.g. "python"
    # code_fix: the buggy/incomplete code shown to the student. code_write: an
    # optional template (e.g. input-reading skeleton); usually empty.
    starter_code: str | None = None
    test_cases: list[CodeTestCase] | None = None  # coding types: hidden cases used to auto-grade submissions
    # code_write only: framed as a real-world / company-interview scenario
    # rather than a plain "write a program that..." task.
    scenario_based: bool = False

    # How the question entered the bank: "generated" by the AI pipeline or
    # "manual" (written by the teacher, classified by AI). None = older questions.
    origin: Literal["generated", "manual"] | None = None

    difficulty_score: float | None = None  # 1-10, set by difficulty scorer (Phase 5)
    embedding_id: str | None = None  # reference into the vector store
    is_duplicate_of: str | None = None  # id of the original question, if flagged

    # Optional teacher override; when unset the category is derived from
    # question_type + bloom_level (see app.schemas.skill).
    skill_category: SkillCategory | None = None

    provenance: QuestionProvenance | None = None  # set for questions generated after provenance was recorded
    derived_from: str | None = None  # id of the question this one was copied from (e.g. marks edited for one paper)

    source_document: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def effective_skill_category(self) -> SkillCategory:
        return resolve_skill_category(self.question_type.value, int(self.bloom_level), self.skill_category)
