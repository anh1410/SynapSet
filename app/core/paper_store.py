import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.schemas.paper_blueprint import PaperBlueprint


class PaperStore:
    """JSON-file-backed store for saved exam paper blueprints (draft/exported)."""

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.blueprints: dict[str, PaperBlueprint] = self._load()

    def _load(self) -> dict[str, PaperBlueprint]:
        if self.persist_path.exists():
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            return {row["id"]: PaperBlueprint.model_validate(row) for row in data}
        return {}

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [b.model_dump(mode="json") for b in self.blueprints.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, blueprint: PaperBlueprint) -> None:
        blueprint.updated_at = datetime.now(UTC)
        self.blueprints[blueprint.id] = blueprint
        self.save()

    def remove(self, blueprint_id: str) -> bool:
        if blueprint_id in self.blueprints:
            del self.blueprints[blueprint_id]
            self.save()
            return True
        return False

    def list(self) -> list[PaperBlueprint]:
        return sorted(self.blueprints.values(), key=lambda b: b.updated_at, reverse=True)

    def get(self, blueprint_id: str) -> PaperBlueprint | None:
        return self.blueprints.get(blueprint_id)


@lru_cache
def get_paper_store() -> PaperStore:
    settings = get_settings()
    return PaperStore(settings.paper_store_path)
