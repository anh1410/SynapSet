import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.subject import Subject


class SubjectStore:
    """JSON-file-backed registry of subjects, each owned by a teacher."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.subjects: dict[str, Subject] = self._load()

    def _load(self) -> dict[str, Subject]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Subject.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.model_dump(mode="json") for s in self.subjects.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, subject: Subject) -> None:
        self.subjects[subject.id] = subject
        self.save()

    def get(self, subject_id: str) -> Subject | None:
        return self.subjects.get(subject_id)

    def remove(self, subject_id: str) -> bool:
        if subject_id in self.subjects:
            del self.subjects[subject_id]
            self.save()
            return True
        return False

    def list_by_teacher(self, teacher_id: str) -> list[Subject]:
        return sorted(
            (s for s in self.subjects.values() if s.teacher_id == teacher_id),
            key=lambda s: s.created_at,
        )


@lru_cache
def get_subject_store() -> SubjectStore:
    settings = get_settings()
    return SubjectStore(settings.subject_store_path)
