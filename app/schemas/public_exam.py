"""Student-facing views of an Exam/Question — stripped of everything that
would let a student see the answer key (correct_answer, test_cases,
difficulty internals, password) before or during the attempt."""

from pydantic import BaseModel

from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType


class PublicQuestion(BaseModel):
    id: str
    text: str
    question_type: QuestionType
    marks: int
    bloom_level: BloomLevel
    options: list[str] | None = None  # mcq/fill_in_blank choices (no correct_answer)
    code_language: str | None = None
    starter_code: str | None = None  # code_fix only (no test_cases/correct_answer)

    @classmethod
    def from_question(cls, q: Question) -> "PublicQuestion":
        return cls(
            id=q.id,
            text=q.text,
            question_type=q.question_type,
            marks=q.marks,
            bloom_level=q.bloom_level,
            options=q.options,
            code_language=q.code_language,
            starter_code=q.starter_code,
        )


class PublicExam(BaseModel):
    id: str
    name: str
    duration_minutes: int | None
    total_marks: int
    questions: list[PublicQuestion]
