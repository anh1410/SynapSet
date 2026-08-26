from functools import lru_cache

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import get_settings


@lru_cache
def get_chroma_client() -> chromadb.ClientAPI:
    settings = get_settings()
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_collection(subject_id: str) -> Collection:
    """Get (or create) the collection that stores syllabus chunk embeddings
    for one subject. Each subject gets its own collection so retrieval never
    surfaces content from a different subject's uploads."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=f"subject_{subject_id}",
        metadata={"hnsw:space": "cosine"},
    )
