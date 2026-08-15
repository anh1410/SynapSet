from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import graph, paper, questions
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=f"{settings.app_name} API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"] if settings.environment == "development" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph.router)
app.include_router(questions.router)
app.include_router(paper.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
