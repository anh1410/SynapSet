from fastapi import FastAPI

from app.api import graph, paper, questions
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=f"{settings.app_name} API", version="0.1.0")

app.include_router(graph.router)
app.include_router(questions.router)
app.include_router(paper.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
