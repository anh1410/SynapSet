import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.submission import Submission


class SubmissionStore:
    """JSON-file-backed store for graded student exam submissions."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.submissions: dict[str, Submission] = self._load()

    def _load(self) -> dict[str, Submission]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: Submission.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.model_dump(mode="json") for s in self.submissions.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, submission: Submission) -> None:
        self.submissions[submission.id] = submission
        self.save()

    def list_by_exam(self, exam_id: str) -> list[Submission]:
        return sorted(
            (s for s in self.submissions.values() if s.exam_id == exam_id),
            key=lambda s: s.submitted_at,
            reverse=True,
        )


@lru_cache
def get_submission_store() -> SubmissionStore:
    settings = get_settings()
    return SubmissionStore(settings.submission_store_path)
