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

    # Question paper patterns (MSE/SEE templates)
    pattern_store_path: str = str(BASE_DIR / "data" / "exam_patterns.json")

    # Graded student submissions
    submission_store_path: str = str(BASE_DIR / "data" / "submissions.json")

    # Students' exam attempts (server-recorded start times)
    attempt_store_path: str = str(BASE_DIR / "data" / "attempts.json")
    # Slack after an attempt's deadline for network latency before a submission is refused.
    submission_grace_seconds: int = 30

    # Assessment-intelligence thresholds (all overridable via .env)
    recent_use_days: int = 30  # "recently used" window for the question bank / assembler
    frequent_use_count: int = 3  # used in at least this many published exams = "frequently used"
    question_min_responses: int = 5  # graded responses before a per-question statistic is shown
    calibration_min_questions: int = 4  # questions (each with enough responses) before comparing predicted vs actual difficulty
    topic_min_questions: int = 3  # fewer bank questions than this on a topic = coverage risk
    topic_risk_percent: float = 50.0  # class score below this on a topic (with enough answers) = performance risk

    # Teacher accounts
    teacher_store_path: str = str(BASE_DIR / "data" / "teachers.json")

    # Subjects (each teacher's separate, isolated workspaces)
    subject_store_path: str = str(BASE_DIR / "data" / "subjects.json")

    # Student accounts + enrolments (student dashboard)
    student_store_path: str = str(BASE_DIR / "data" / "students.json")

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 60 * 24 * 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
