import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.attempt import Attempt


class AttemptStore:
    """JSON-file-backed store for students' exam attempts (server-side start times)."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.attempts: dict[str, Attempt] = self._load()

    def _load(self) -> dict[str, Attempt]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Attempt.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [a.model_dump(mode="json") for a in self.attempts.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, attempt: Attempt) -> None:
        self.attempts[attempt.id] = attempt
        self.save()

    def get(self, attempt_id: str) -> Attempt | None:
        return self.attempts.get(attempt_id)

    def find(self, exam_id: str, student_key: str) -> Attempt | None:
        return next(
            (a for a in self.attempts.values() if a.exam_id == exam_id and a.student_key == student_key),
            None,
        )

    def list_by_exam(self, exam_id: str) -> list[Attempt]:
        return sorted((a for a in self.attempts.values() if a.exam_id == exam_id), key=lambda a: a.started_at)


@lru_cache
def get_attempt_store() -> AttemptStore:
    settings = get_settings()
    return AttemptStore(settings.attempt_store_path)
