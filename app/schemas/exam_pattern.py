"""Question paper patterns (MSE / SEE templates) that drive constraint-based
assessment assembly (app.services.pattern_assembly).

Distributions are stored as lists of {key, percent} rows rather than dicts so
they round-trip cleanly through JSON, the form UI, and Gemini structured
output (which can't express free-form dict keys).
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from app.schemas.skill import DifficultyBucket

PatternExamType = Literal["MSE", "SEE"]

_PERCENT_TOLERANCE = 1.0  # distributions must add up to 100 +/- this


class PatternSection(BaseModel):
    name: str = Field(min_length=1, description='e.g. "Part A"')
    instructions: str = ""
    num_questions: int = Field(ge=1)
    marks_per_question: int = Field(ge=1)
    # Empty list = any question type / any Bloom's level is acceptable.
    question_types: list[QuestionType] = Field(default_factory=list)
    bloom_levels: list[BloomLevel] = Field(default_factory=list)

    @property
    def total_marks(self) -> int:
        return self.num_questions * self.marks_per_question


class BloomShare(BaseModel):
    bloom_level: BloomLevel
    percent: float = Field(ge=0, le=100)


class DifficultyShare(BaseModel):
    difficulty: DifficultyBucket
    percent: float = Field(ge=0, le=100)


class PatternUnit(BaseModel):
    """A syllabus unit, defined as a group of knowledge-graph topics. A question
    belongs to a unit when it's tagged with one of the unit's topics (or its
    explicit Question.unit matches)."""

    unit: int = Field(ge=1)
    name: str = ""
    topic_ids: list[str] = Field(default_factory=list)
    percent: float = Field(ge=0, le=100, description="Share of total marks drawn from this unit")


class CoRequirement(BaseModel):
    """A course outcome the paper must assess: at least `min_questions`
    questions tagged with it and/or at least `min_percent` of total marks."""

    co_code: str = Field(min_length=1)
    min_questions: int = Field(default=0, ge=0)
    min_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _has_a_target(self):
        if not self.min_questions and not self.min_percent:
            raise ValueError(f"{self.co_code}: set a minimum number of questions or a minimum % of marks")
        return self


class ExamPatternFields(BaseModel):
    """Everything a teacher edits. Shared by create/update requests, imported
    drafts, and the stored ExamPattern."""

    name: str = Field(min_length=1)
    exam_type: PatternExamType
    description: str = ""
    total_marks: int = Field(ge=1)
    duration_minutes: int = Field(ge=1)
    sections: list[PatternSection] = Field(min_length=1)
    bloom_distribution: list[BloomShare] = Field(default_factory=list)
    difficulty_distribution: list[DifficultyShare] = Field(default_factory=list)
    units: list[PatternUnit] = Field(default_factory=list)
    co_requirements: list[CoRequirement] = Field(default_factory=list)
    # How far (as % of total marks) a Bloom/difficulty/unit share may drift from its target.
    tolerance_percent: float = Field(default=10.0, ge=0, le=50)

    @property
    def num_questions(self) -> int:
        return sum(s.num_questions for s in self.sections)

    @model_validator(mode="after")
    def _check_consistency(self):
        section_marks = sum(s.total_marks for s in self.sections)
        if section_marks != self.total_marks:
            raise ValueError(
                f"Sections add up to {section_marks} marks but the pattern's total is {self.total_marks}"
            )
        for label, rows in (
            ("Bloom's distribution", self.bloom_distribution),
            ("Difficulty distribution", self.difficulty_distribution),
            ("Unit distribution", self.units),
        ):
            if rows:
                total = sum(r.percent for r in rows)
                if abs(total - 100) > _PERCENT_TOLERANCE:
                    raise ValueError(f"{label} adds up to {total:g}%, expected 100%")
        if len({b.bloom_level for b in self.bloom_distribution}) != len(self.bloom_distribution):
            raise ValueError("Each Bloom's level may appear only once in the distribution")
        if len({d.difficulty for d in self.difficulty_distribution}) != len(self.difficulty_distribution):
            raise ValueError("Each difficulty level may appear only once in the distribution")
        if len({u.unit for u in self.units}) != len(self.units):
            raise ValueError("Unit numbers must be unique")
        if len({c.co_code for c in self.co_requirements}) != len(self.co_requirements):
            raise ValueError("Each course outcome may appear only once")
        return self


class ExamPattern(ExamPatternFields):
    id: str
    teacher_id: str
    subject_id: str
    source_filename: str | None = None  # set when the pattern was imported from a document
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def pattern_presets() -> list[ExamPatternFields]:
    """Starting templates for the two institutional exam types. Teachers are
    expected to adjust them to their institution's actual scheme."""
    B = BloomLevel
    Q = QuestionType
    return [
        ExamPatternFields(
            name="Mid-Semester Examination",
            exam_type="MSE",
            description="Starting template - adjust sections and weights to your institution's MSE scheme.",
            total_marks=50,
            duration_minutes=90,
            sections=[
                PatternSection(
                    name="Part A",
                    instructions="Answer all questions.",
                    num_questions=10,
                    marks_per_question=1,
                    question_types=[Q.MCQ, Q.FILL_IN_BLANK],
                    bloom_levels=[B.REMEMBER, B.UNDERSTAND],
                ),
                PatternSection(
                    name="Part B",
                    instructions="Answer all questions.",
                    num_questions=5,
                    marks_per_question=4,
                    question_types=[Q.SHORT_ANSWER, Q.NUMERICAL, Q.CODE_FIX],
                    bloom_levels=[B.UNDERSTAND, B.APPLY],
                ),
                PatternSection(
                    name="Part C",
                    instructions="Answer all questions.",
                    num_questions=2,
                    marks_per_question=10,
                    question_types=[Q.LONG_ANSWER, Q.CODE_FIX],
                    bloom_levels=[B.APPLY, B.ANALYZE],
                ),
            ],
            bloom_distribution=[
                BloomShare(bloom_level=B.REMEMBER, percent=10),
                BloomShare(bloom_level=B.UNDERSTAND, percent=30),
                BloomShare(bloom_level=B.APPLY, percent=40),
                BloomShare(bloom_level=B.ANALYZE, percent=20),
            ],
            difficulty_distribution=[
                DifficultyShare(difficulty="easy", percent=30),
                DifficultyShare(difficulty="medium", percent=50),
                DifficultyShare(difficulty="hard", percent=20),
            ],
            tolerance_percent=10,
        ),
        ExamPatternFields(
            name="Semester-End Examination",
            exam_type="SEE",
            description="Starting template - adjust sections and weights to your institution's SEE scheme.",
            total_marks=100,
            duration_minutes=180,
            sections=[
                PatternSection(
                    name="Part A",
                    instructions="Answer all questions.",
                    num_questions=10,
                    marks_per_question=2,
                    question_types=[Q.MCQ, Q.FILL_IN_BLANK, Q.SHORT_ANSWER],
                    bloom_levels=[B.REMEMBER, B.UNDERSTAND],
                ),
                PatternSection(
                    name="Part B",
                    instructions="Answer all questions.",
                    num_questions=8,
                    marks_per_question=5,
                    question_types=[Q.SHORT_ANSWER, Q.NUMERICAL, Q.CODE_FIX],
                    bloom_levels=[B.UNDERSTAND, B.APPLY, B.ANALYZE],
                ),
                PatternSection(
                    name="Part C",
                    instructions="Answer all questions.",
                    num_questions=4,
                    marks_per_question=10,
                    question_types=[Q.LONG_ANSWER, Q.CODE_FIX],
                    bloom_levels=[B.APPLY, B.ANALYZE, B.EVALUATE],
                ),
            ],
            bloom_distribution=[
                BloomShare(bloom_level=B.REMEMBER, percent=10),
                BloomShare(bloom_level=B.UNDERSTAND, percent=20),
                BloomShare(bloom_level=B.APPLY, percent=35),
                BloomShare(bloom_level=B.ANALYZE, percent=25),
                BloomShare(bloom_level=B.EVALUATE, percent=10),
            ],
            difficulty_distribution=[
                DifficultyShare(difficulty="easy", percent=25),
                DifficultyShare(difficulty="medium", percent=50),
                DifficultyShare(difficulty="hard", percent=25),
            ],
            tolerance_percent=10,
        ),
    ]
