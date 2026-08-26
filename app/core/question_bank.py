import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.question import Question


class QuestionBank:
    """JSON-file-backed store for generated questions, so duplicate detection
    and paper optimization have a persistent pool to work against."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.questions: dict[str, Question] = self._load()

    def _load(self) -> dict[str, Question]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Question.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [q.model_dump(mode="json") for q in self.questions.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, question: Question) -> None:
        self.questions[question.id] = question
        self.save()

    def add_many(self, questions: list[Question]) -> None:
        for q in questions:
            self.questions[q.id] = q
        self.save()

    def remove(self, question_id: str) -> bool:
        if question_id in self.questions:
            del self.questions[question_id]
            self.save()
            return True
        return False

    def list(self) -> list[Question]:
        return list(self.questions.values())

    def get(self, question_id: str) -> Question | None:
        return self.questions.get(question_id)


@lru_cache
def get_question_bank(subject_id: str) -> QuestionBank:
    """One question bank per subject, so generated questions never leak across subjects."""
    settings = get_settings()
    path = Path(settings.question_bank_dir) / f"{subject_id}.json"
    return QuestionBank(str(path))
