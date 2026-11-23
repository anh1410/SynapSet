from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, auth, exams, graph, paper_review, patterns, questions, student_portal, subjects, submissions
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
app.include_router(paper_review.router)
app.include_router(submissions.router)
app.include_router(patterns.router)
app.include_router(analytics.router)
app.include_router(student_portal.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


DIST = Path(__file__).resolve().parent.parent / "dist"
if DIST.is_dir():  # production image: serve the built React app from the same origin
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (DIST / path).resolve()
        return FileResponse(file if file.is_file() and DIST in file.parents else DIST / "index.html")
