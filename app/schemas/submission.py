from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.schemas.question import QuestionType
from app.schemas.skill import SkillCategory


class AnswerSubmission(BaseModel):
    question_id: str
    answer: str


class GradedAnswer(BaseModel):
    question_id: str
    question_type: QuestionType
    auto_graded: bool
    correct: bool | None = None  # None when it needs manual grading (short_answer/long_answer)
    marks_awarded: int
    max_marks: int
    detail: str

    # What the student actually wrote - needed so a teacher can manually grade
    # short/long answers. None on submissions recorded before this was stored.
    answer: str | None = None
    manually_graded: bool = False
    feedback: str | None = None

    # Snapshot of the question's metadata at submission time, so performance
    # analytics stay correct even if the question is later edited or deleted
    # from the bank. All optional: older submissions fall back to the bank.
    bloom_level: int | None = None
    topic_ids: list[str] | None = None
    skill_category: SkillCategory | None = None
    difficulty_score: float | None = None
    test_cases_passed: int | None = None  # code_fix only
    test_cases_total: int | None = None  # code_fix only

    @property
    def is_graded(self) -> bool:
        return self.auto_graded or self.manually_graded


class Submission(BaseModel):
    id: str
    exam_id: str
    student_name: str
    student_identifier: str | None = None
    answers: list[GradedAnswer] = Field(default_factory=list)
    total_marks_awarded: int
    total_max_marks: int
    # False while any answer still needs a human to grade it (kept under its
    # original name for API compatibility; manual grading flips it to True).
    fully_auto_graded: bool
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def recompute_totals(self) -> None:
        self.total_marks_awarded = sum(a.marks_awarded for a in self.answers)
        self.total_max_marks = sum(a.max_marks for a in self.answers)
        self.fully_auto_graded = all(a.is_graded for a in self.answers)
