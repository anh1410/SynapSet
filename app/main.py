from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, exams, graph, questions, subjects, submissions
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=f"{settings.app_name} API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # In dev, any localhost port is allowed - not just this teacher frontend's
    # 5173, since the student-side app (separate project/port) also calls
    # this same backend for exam password-verify/submit.
    allow_origins=["http://localhost:5173"] if settings.environment != "development" else [],
    allow_origin_regex=r"http://localhost:\d+" if settings.environment == "development" else None,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(subjects.router)
app.include_router(graph.router)
app.include_router(questions.router)
app.include_router(exams.router)
app.include_router(submissions.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
