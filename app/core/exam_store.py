import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.exam import Exam


class ExamStore:
    """JSON-file-backed store for saved exams (weekly quizzes)."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.exams: dict[str, Exam] = self._load()

    def _load(self) -> dict[str, Exam]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Exam.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [e.model_dump(mode="json") for e in self.exams.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, exam: Exam) -> None:
        exam.updated_at = datetime.now(UTC)
        self.exams[exam.id] = exam
        self.save()

    def remove(self, exam_id: str) -> bool:
        if exam_id in self.exams:
            del self.exams[exam_id]
            self.save()
            return True
        return False

    def list_by_teacher(self, teacher_id: str) -> list[Exam]:
        return sorted(
            (e for e in self.exams.values() if e.teacher_id == teacher_id),
            key=lambda e: e.updated_at,
            reverse=True,
        )

    def list_by_subject(self, subject_id: str) -> list[Exam]:
        return sorted(
            (e for e in self.exams.values() if e.subject_id == subject_id),
            key=lambda e: e.updated_at,
            reverse=True,
        )

    def get(self, exam_id: str) -> Exam | None:
        return self.exams.get(exam_id)


@lru_cache
def get_exam_store() -> ExamStore:
    settings = get_settings()
    return ExamStore(settings.exam_store_path)
