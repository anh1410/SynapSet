import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.document import UploadedDocument


class DocumentStore:
    """JSON-file-backed registry of uploaded documents and their ingestion status."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.documents: dict[str, UploadedDocument] = self._load()

    def _load(self) -> dict[str, UploadedDocument]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: UploadedDocument.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [d.model_dump(mode="json") for d in self.documents.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, document: UploadedDocument) -> None:
        self.documents[document.id] = document
        self.save()

    def remove(self, document_id: str) -> bool:
        if document_id in self.documents:
            del self.documents[document_id]
            self.save()
            return True
        return False

    def list(self) -> list[UploadedDocument]:
        return sorted(self.documents.values(), key=lambda d: d.uploaded_at, reverse=True)


@lru_cache
def get_document_store() -> DocumentStore:
    settings = get_settings()
    return DocumentStore(settings.document_store_path)
