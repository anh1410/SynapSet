import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.exam_pattern import ExamPattern


class PatternStore:
    """JSON-file-backed store for question paper patterns (MSE/SEE templates)."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.patterns: dict[str, ExamPattern] = self._load()

    def _load(self) -> dict[str, ExamPattern]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: ExamPattern.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [p.model_dump(mode="json") for p in self.patterns.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, pattern: ExamPattern) -> None:
        pattern.updated_at = datetime.now(UTC)
        self.patterns[pattern.id] = pattern
        self.save()

    def get(self, pattern_id: str) -> ExamPattern | None:
        return self.patterns.get(pattern_id)

    def remove(self, pattern_id: str) -> bool:
        if pattern_id in self.patterns:
            del self.patterns[pattern_id]
            self.save()
            return True
        return False

    def list_by_subject(self, subject_id: str) -> list[ExamPattern]:
        return sorted(
            (p for p in self.patterns.values() if p.subject_id == subject_id),
            key=lambda p: (p.exam_type, p.name.lower()),
        )


@lru_cache
def get_pattern_store() -> PatternStore:
    settings = get_settings()
    return PatternStore(settings.pattern_store_path)
