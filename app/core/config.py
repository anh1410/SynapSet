from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "SynapSet"
    environment: str = "development"
    debug: bool = True

    # Google Gemini
    google_api_key: str = ""
    embedding_model: str = "gemini-embedding-001"
    generation_model: str = "gemini-flash-lite-latest"

    # Neo4j (optional; falls back to NetworkX in-memory/pickle if unset)
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""

    # Vector store (ChromaDB)
    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma")
    chroma_collection_name: str = "syllabus_chunks"

    # File storage
    upload_dir: str = str(BASE_DIR / "data" / "uploads")

    # Graph storage (used when Neo4j is not configured)
    graph_store_path: str = str(BASE_DIR / "data" / "knowledge_graph.gpickle")

    # Question bank storage
    question_bank_path: str = str(BASE_DIR / "data" / "question_bank.json")

    # Paper export output
    export_dir: str = str(BASE_DIR / "data" / "exports")


@lru_cache
def get_settings() -> Settings:
    return Settings()
