from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.question_bank import get_question_bank
from app.schemas.constraints import PaperConstraints
from app.schemas.question import Question
from app.services.paper_export import export_paper_docx, export_paper_pdf
from app.services.paper_optimization import optimize_paper

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])


class OptimizePaperRequest(BaseModel):
    constraints: PaperConstraints
    question_ids: list[str] | None = None


class OptimizePaperResponse(BaseModel):
    status: str
    selected: list[Question]


@router.post("/optimize", response_model=OptimizePaperResponse)
def optimize(request: OptimizePaperRequest) -> OptimizePaperResponse:
    """Run the CP-SAT solver over the question bank (or a given subset) against hard constraints."""
    bank = get_question_bank()
    if request.question_ids:
        candidates = [q for qid in request.question_ids if (q := bank.get(qid)) is not None]
    else:
        candidates = bank.list()

    if not candidates:
        raise HTTPException(status_code=400, detail="No candidate questions available")

    result = optimize_paper(candidates, request.constraints)
    return OptimizePaperResponse(status=result.status, selected=result.selected)


class ExportPaperRequest(BaseModel):
    title: str
    questions: list[Question]
    format: str = "pdf"


@router.post("/export")
def export(request: ExportPaperRequest) -> FileResponse:
    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if c.isalnum() else "_" for c in request.title)[:50] or "paper"

    if request.format == "pdf":
        path = export_dir / f"{safe_title}.pdf"
        export_paper_pdf(request.questions, request.title, str(path))
        media_type = "application/pdf"
    elif request.format == "docx":
        path = export_dir / f"{safe_title}.docx"
        export_paper_docx(request.questions, request.title, str(path))
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'docx'")

    return FileResponse(path, media_type=media_type, filename=path.name)
