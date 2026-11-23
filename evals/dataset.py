"""Golden dataset loading and deterministic (no-LLM, no-network) checks for generated questions."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType

GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"
BLANK_MARKER = "_____"


@dataclass(frozen=True)
class GoldenCase:
    id: str
    topic: str
    bloom_level: str
    question_type: str
    marks: int
    syllabus: str
    prerequisites: tuple[str, ...] = ()

    @property
    def source_document(self) -> str:
        return f"{self.id}.txt"

    @property
    def prompt(self) -> str:
        qtype = self.question_type.replace("_", " ")
        return (
            f"Write a {qtype} exam question at Bloom's level {self.bloom_level} "
            f"on the topic '{self.topic}', worth {self.marks} marks."
        )


def load_golden_dataset(limit: int | None = None) -> list[GoldenCase]:
    """Load the golden cases. `limit` (or the EVAL_CASE_LIMIT env var) keeps only the first N."""
    raw = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases = [GoldenCase(**{**item, "prerequisites": tuple(item.get("prerequisites", []))}) for item in raw]
    if limit is None and os.environ.get("EVAL_CASE_LIMIT"):
        limit = int(os.environ["EVAL_CASE_LIMIT"])
    return cases[:limit] if limit else cases


def render_question(question: Question, include_options: bool = True) -> str:
    """Flatten a question and its model answer into text for the LLM judges.

    The model answer is included on purpose: it is where most factual claims live, so
    groundedness and hallucination checks have something real to verify. Judges are given
    `include_options=False`, because deliberately wrong MCQ distractors would otherwise be
    scored as unsupported claims.
    """
    parts = [f"Question: {question.text}"]
    if include_options and question.options:
        parts.append("Options:\n" + "\n".join(f"- {option}" for option in question.options))
    if question.correct_answer:
        parts.append(f"Model answer: {question.correct_answer}")
    return "\n".join(parts)


def structural_problems(case: GoldenCase, question: Question) -> list[str]:
    """Deterministic format and instruction-following checks. An empty list means the question is well-formed."""
    problems: list[str] = []
    if not question.text.strip():
        problems.append("question text is empty")
    if question.question_type != QuestionType(case.question_type):
        problems.append(f"question_type is {question.question_type.value}, requested {case.question_type}")
    if question.bloom_level != BloomLevel[case.bloom_level]:
        problems.append(f"bloom_level is {question.bloom_level.name}, requested {case.bloom_level}")
    if question.marks != case.marks:
        problems.append(f"marks is {question.marks}, requested {case.marks}")

    if question.question_type in (QuestionType.MCQ, QuestionType.FILL_IN_BLANK):
        options = question.options or []
        if len(options) != 4:
            problems.append(f"expected 4 options, got {len(options)}")
        if question.correct_answer not in options:
            problems.append("correct_answer is not one of the options")
    elif not (question.correct_answer or "").strip():
        problems.append("missing model answer")

    if question.question_type == QuestionType.FILL_IN_BLANK and BLANK_MARKER not in question.text:
        problems.append(f"fill_in_blank question has no '{BLANK_MARKER}' placeholder")
    return problems
