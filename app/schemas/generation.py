from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.question import CodeTestCase, QuestionType

BloomLevelName = Literal["REMEMBER", "UNDERSTAND", "APPLY", "ANALYZE", "EVALUATE", "CREATE"]


class GeneratedQuestionDraft(BaseModel):
    text: str
    question_type: QuestionType
    bloom_level: BloomLevelName
    marks: int
    options: list[str] | None = None
    correct_answer: str | None = None
    code_language: str | None = None
    starter_code: str | None = None
    test_cases: list[CodeTestCase] | None = None
    topic_names: list[str] = Field(default_factory=list)
    co_codes: list[str] = Field(default_factory=list)


class QuestionDraftBatch(BaseModel):
    questions: list[GeneratedQuestionDraft] = Field(default_factory=list)
