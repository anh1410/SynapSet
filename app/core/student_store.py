import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.student import Student


class StudentStore:
    """JSON-file-backed registry of student accounts (and their enrolments)."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.students: dict[str, Student] = self._load()

    def _load(self) -> dict[str, Student]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Student.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.model_dump(mode="json") for s in self.students.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, student: Student) -> None:
        self.students[student.id] = student
        self.save()

    def get(self, student_id: str) -> Student | None:
        return self.students.get(student_id)

    def get_by_email(self, email: str) -> Student | None:
        email_lower = email.strip().lower()
        return next((s for s in self.students.values() if s.email.lower() == email_lower), None)

    def get_by_key(self, key: str) -> Student | None:
        """The account whose roll number maps to this exam identity key."""
        return next((s for s in self.students.values() if s.key == key), None)

    def list_by_subject(self, subject_id: str) -> list[Student]:
        return sorted((s for s in self.students.values() if subject_id in s.subject_ids), key=lambda s: s.name.lower())


@lru_cache
def get_student_store() -> StudentStore:
    settings = get_settings()
    return StudentStore(settings.student_store_path)
