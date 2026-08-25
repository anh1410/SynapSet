import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.teacher import Teacher


class TeacherStore:
    """JSON-file-backed registry of teacher accounts."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.teachers: dict[str, Teacher] = self._load()

    def _load(self) -> dict[str, Teacher]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Teacher.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [t.model_dump(mode="json") for t in self.teachers.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, teacher: Teacher) -> None:
        self.teachers[teacher.id] = teacher
        self.save()

    def get(self, teacher_id: str) -> Teacher | None:
        return self.teachers.get(teacher_id)

    def get_by_email(self, email: str) -> Teacher | None:
        email_lower = email.lower()
        for teacher in self.teachers.values():
            if teacher.email.lower() == email_lower:
                return teacher
        return None

    def list(self) -> list[Teacher]:
        return list(self.teachers.values())


@lru_cache
def get_teacher_store() -> TeacherStore:
    settings = get_settings()
    return TeacherStore(settings.teacher_store_path)
