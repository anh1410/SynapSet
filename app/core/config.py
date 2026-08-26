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

    # Vector store (ChromaDB) — one collection per subject
    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma")

    # File storage
    upload_dir: str = str(BASE_DIR / "data" / "uploads")

    # Graph storage (used when Neo4j is not configured) — one pickle file per subject
    graph_store_dir: str = str(BASE_DIR / "data" / "graphs")

    # Question bank storage — one JSON file per subject
    question_bank_dir: str = str(BASE_DIR / "data" / "question_banks")

    # Uploaded document registry — one JSON file per subject
    document_store_dir: str = str(BASE_DIR / "data" / "documents")

    # Saved exams (weekly quizzes)
    exam_store_path: str = str(BASE_DIR / "data" / "exams.json")

    # Graded student submissions
    submission_store_path: str = str(BASE_DIR / "data" / "submissions.json")

    # Teacher accounts
    teacher_store_path: str = str(BASE_DIR / "data" / "teachers.json")

    # Subjects (each teacher's separate, isolated workspaces)
    subject_store_path: str = str(BASE_DIR / "data" / "subjects.json")

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 60 * 24 * 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
