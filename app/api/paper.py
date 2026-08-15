import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.paper_store import get_paper_store
from app.core.question_bank import get_question_bank
from app.schemas.constraints import PaperConstraints
from app.schemas.paper_blueprint import BlueprintStatus, PaperBlueprint
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


def _write_export_file(title: str, questions: list[Question], fmt: str) -> Path:
    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if c.isalnum() else "_" for c in title)[:50] or "paper"

    if fmt == "pdf":
        path = export_dir / f"{safe_title}.pdf"
        export_paper_pdf(questions, title, str(path))
    elif fmt == "docx":
        path = export_dir / f"{safe_title}.docx"
        export_paper_docx(questions, title, str(path))
    else:
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'docx'")
    return path


_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ExportPaperRequest(BaseModel):
    title: str
    questions: list[Question]
    format: str = "pdf"


@router.post("/export")
def export(request: ExportPaperRequest) -> FileResponse:
    """Ad-hoc export of an arbitrary question list, without saving a blueprint."""
    path = _write_export_file(request.title, request.questions, request.format)
    return FileResponse(path, media_type=_MEDIA_TYPES[request.format], filename=path.name)


class CreateBlueprintRequest(BaseModel):
    name: str
    total_marks: int
    duration_minutes: int | None = None
    question_ids: list[str] = []


class UpdateBlueprintRequest(BaseModel):
    name: str | None = None
    total_marks: int | None = None
    duration_minutes: int | None = None
    question_ids: list[str] | None = None
    status: BlueprintStatus | None = None


@router.post("/blueprints", response_model=PaperBlueprint)
def create_blueprint(request: CreateBlueprintRequest) -> PaperBlueprint:
    blueprint = PaperBlueprint(
        id=str(uuid.uuid4()),
        name=request.name,
        total_marks=request.total_marks,
        duration_minutes=request.duration_minutes,
        question_ids=request.question_ids,
    )
    get_paper_store().add(blueprint)
    return blueprint


@router.get("/blueprints", response_model=list[PaperBlueprint])
def list_blueprints() -> list[PaperBlueprint]:
    return get_paper_store().list()


class BlueprintDetail(BaseModel):
    blueprint: PaperBlueprint
    questions: list[Question]


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintDetail)
def get_blueprint(blueprint_id: str) -> BlueprintDetail:
    blueprint = get_paper_store().get(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    bank = get_question_bank()
    questions = [q for qid in blueprint.question_ids if (q := bank.get(qid)) is not None]
    return BlueprintDetail(blueprint=blueprint, questions=questions)


@router.patch("/blueprints/{blueprint_id}", response_model=PaperBlueprint)
def update_blueprint(blueprint_id: str, request: UpdateBlueprintRequest) -> PaperBlueprint:
    store = get_paper_store()
    blueprint = store.get(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    update_data = request.model_dump(exclude_unset=True)
    updated = blueprint.model_copy(update=update_data)
    store.add(updated)
    return updated


@router.delete("/blueprints/{blueprint_id}")
def delete_blueprint(blueprint_id: str) -> dict:
    if not get_paper_store().remove(blueprint_id):
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return {"deleted": blueprint_id}


@router.get("/blueprints/{blueprint_id}/export")
def export_blueprint(blueprint_id: str, format: str = "pdf") -> FileResponse:
    store = get_paper_store()
    blueprint = store.get(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    bank = get_question_bank()
    questions = [q for qid in blueprint.question_ids if (q := bank.get(qid)) is not None]
    path = _write_export_file(blueprint.name, questions, format)

    blueprint.status = "exported"
    store.add(blueprint)

    return FileResponse(path, media_type=_MEDIA_TYPES[format], filename=path.name)
