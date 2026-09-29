import json
import secrets
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.subject import Subject

# No 0/O, 1/I/L: join codes are read off a board and typed by students.
_JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 7


def new_join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def normalize_join_code(code: str) -> str:
    return "".join(code.split()).replace("-", "").upper()


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

    def get_by_join_code(self, code: str) -> Subject | None:
        code = normalize_join_code(code)
        return next((s for s in self.subjects.values() if s.join_code == code), None) if code else None

    def assign_join_code(self, subject: Subject) -> Subject:
        """Give the subject a fresh, unique join code (replacing any old one) and save."""
        taken = {s.join_code for s in self.subjects.values()}
        code = new_join_code()
        while code in taken:
            code = new_join_code()
        subject.join_code = code
        self.add(subject)
        return subject

    def list_by_teacher(self, teacher_id: str) -> list[Subject]:
        return sorted(
            (s for s in self.subjects.values() if s.teacher_id == teacher_id),
            key=lambda s: s.created_at,
        )


@lru_cache
def get_subject_store() -> SubjectStore:
    settings = get_settings()
    return SubjectStore(settings.subject_store_path)
