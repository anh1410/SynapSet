from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.schemas.question import QuestionType


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


class Submission(BaseModel):
    id: str
    exam_id: str
    student_name: str
    student_identifier: str | None = None
    answers: list[GradedAnswer] = Field(default_factory=list)
    total_marks_awarded: int
    total_max_marks: int
    fully_auto_graded: bool  # False if any question still needs a human to grade it
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
