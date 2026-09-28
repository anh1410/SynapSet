import tempfile
import uuid
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_current_teacher, require_subject
from app.core.config import get_settings
from app.core.exam_store import get_exam_store
from app.core.graph_store import course_outcome_node_ids, get_graph_store
from app.core.pattern_store import get_pattern_store
from app.core.question_bank import get_question_bank
from app.schemas.exam_pattern import ExamPattern, ExamPatternFields, pattern_presets
from app.schemas.teacher import Teacher
from app.services.difficulty_scoring import score_difficulty
from app.services.duplicate_detection import find_duplicates
from app.services.pattern_assembly import (
    AssemblyResult,
    ComplianceReport,
    GapRequest,
    TopicInfo,
    assemble,
    evaluate_selection,
    plan_gap_requests,
)
from app.services.pattern_import import PatternImportResult, import_pattern
from app.services.question_generation import generate_questions
from app.services.question_usage import recently_used_ids

router = APIRouter(prefix="/api/v1/patterns", tags=["patterns"], dependencies=[Depends(get_current_teacher)])


def _require_pattern(pattern_id: str, teacher: Teacher) -> ExamPattern:
    pattern = get_pattern_store().get(pattern_id)
    if pattern is None or pattern.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Pattern not found")
    require_subject(pattern.subject_id, teacher)
    return pattern


@router.get("/presets", response_model=list[ExamPatternFields])
def list_presets() -> list[ExamPatternFields]:
    """Starting MSE/SEE templates for the pattern form."""
    return pattern_presets()


@router.get("", response_model=list[ExamPattern])
def list_patterns(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[ExamPattern]:
    require_subject(subject_id, teacher)
    return [p for p in get_pattern_store().list_by_subject(subject_id) if p.teacher_id == teacher.id]


class CreatePatternRequest(ExamPatternFields):
    subject_id: str
    source_filename: str | None = None


@router.post("", response_model=ExamPattern)
def create_pattern(request: CreatePatternRequest, teacher: Teacher = Depends(get_current_teacher)) -> ExamPattern:
    require_subject(request.subject_id, teacher)
    fields = ExamPatternFields.model_validate(request.model_dump(exclude={"subject_id", "source_filename"}))
    pattern = ExamPattern(
        **fields.model_dump(),
        id=str(uuid.uuid4()),
        teacher_id=teacher.id,
        subject_id=request.subject_id,
        source_filename=request.source_filename,
    )
    get_pattern_store().add(pattern)
    return pattern


@router.get("/{pattern_id}", response_model=ExamPattern)
def get_pattern(pattern_id: str, teacher: Teacher = Depends(get_current_teacher)) -> ExamPattern:
    return _require_pattern(pattern_id, teacher)


@router.put("/{pattern_id}", response_model=ExamPattern)
def update_pattern(
    pattern_id: str, request: ExamPatternFields, teacher: Teacher = Depends(get_current_teacher)
) -> ExamPattern:
    existing = _require_pattern(pattern_id, teacher)
    updated = ExamPattern.model_validate({**existing.model_dump(), **request.model_dump()})
    get_pattern_store().add(updated)
    return updated


@router.delete("/{pattern_id}")
def delete_pattern(pattern_id: str, teacher: Teacher = Depends(get_current_teacher)) -> dict:
    """Exams already built from the pattern keep their questions and exam type;
    they just lose the link back to it."""
    _require_pattern(pattern_id, teacher)
    get_pattern_store().remove(pattern_id)
    return {"deleted": pattern_id}


@router.post("/import", response_model=PatternImportResult)
async def import_pattern_document(
    subject_id: str = Form(...),
    file: UploadFile = File(...),
    exam_type_hint: str = Form(""),
    teacher: Teacher = Depends(get_current_teacher),
) -> PatternImportResult:
    """Read a pattern / scheme-of-examination document (PDF, DOCX, PPTX, TXT)
    and return a *draft* pattern for the teacher to review. Nothing is saved."""
    require_subject(subject_id, teacher)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".pptx", ".txt"}:
        raise HTTPException(status_code=400, detail="Upload a PDF, DOCX, PPTX, or TXT file")
    contents = await file.read()
    tmp_dir = Path(get_settings().upload_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)
    try:
        return import_pattern(str(tmp_path), file.filename or "pattern", get_graph_store(subject_id), exam_type_hint)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pattern import failed: {type(exc).__name__}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


class AssembleRequest(BaseModel):
    # Generate questions (Graph-RAG, same pipeline as the Exam Builder) for
    # sections the bank can't fill, save them to the bank, then re-solve.
    generate_missing: bool = False
    max_generate: int = Field(default=8, ge=1, le=20)
    # Leave out questions that appeared in a published exam within this many days.
    avoid_recent_days: int | None = Field(default=None, ge=1, le=365)


class GeneratedForGap(BaseModel):
    request: GapRequest
    question_id: str | None = None
    skipped_reason: str | None = None


class AssembleResponse(BaseModel):
    assembly: AssemblyResult
    generated: list[GeneratedForGap] = Field(default_factory=list)
    excluded_recent: int = 0  # bank questions left out because they were used recently


def _usage_counts(subject_id: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for exam in get_exam_store().list_by_subject(subject_id):
        counts.update(exam.question_ids)
    return dict(counts)


def _fill_gaps(pattern: ExamPattern, max_generate: int, exclude: set[str] | None = None) -> list[GeneratedForGap]:
    graph_store = get_graph_store(pattern.subject_id)
    bank = get_question_bank(pattern.subject_id)
    graph = graph_store.graph
    counts: Counter[str] = Counter(t for q in bank.list() for t in q.topic_ids)
    course_outcomes = course_outcome_node_ids(graph)
    topics = [
        TopicInfo(
            id=nid,
            name=data.get("name", nid),
            importance=data.get("importance_score", 0.0),
            question_count=counts.get(nid, 0),
        )
        for nid, data in graph.nodes(data=True)
        if nid not in course_outcomes  # COs aren't topics to write questions about
    ]
    results: list[GeneratedForGap] = []
    candidates = [q for q in bank.list() if q.id not in (exclude or set())]
    for req in plan_gap_requests(pattern, candidates, topics, max_generate):
        try:
            drafts = generate_questions(
                topic=req.topic_name,
                graph_store=graph_store,
                subject_id=pattern.subject_id,
                num_questions=1,
                bloom_level=req.bloom_level,
                marks=req.marks,
                question_type=req.question_type,
            )
        except Exception as exc:  # one failed call shouldn't sink the whole assembly
            results.append(GeneratedForGap(request=req, skipped_reason=f"Generation failed: {type(exc).__name__}"))
            continue
        if not drafts:
            results.append(GeneratedForGap(request=req, skipped_reason="No question returned"))
            continue
        question = drafts[0]
        # The model is asked for these, but pin them so the question fits the slot it was generated for.
        question.marks = req.marks
        question.bloom_level = req.bloom_level
        question.unit = req.unit
        if req.topic_id not in question.topic_ids:
            question.topic_ids.insert(0, req.topic_id)
        question.difficulty_score = score_difficulty(question, graph_store).score
        if any(m.is_duplicate for m in find_duplicates(question, bank.list())):
            results.append(GeneratedForGap(request=req, skipped_reason="Near-duplicate of a bank question"))
            continue
        bank.add(question)
        results.append(GeneratedForGap(request=req, question_id=question.id))
    return results


@router.post("/{pattern_id}/assemble", response_model=AssembleResponse)
def assemble_from_pattern(
    pattern_id: str, request: AssembleRequest, teacher: Teacher = Depends(get_current_teacher)
) -> AssembleResponse:
    """Pick questions from the subject's bank that satisfy the pattern. Returns
    the chosen question ids plus a compliance report - it does not create an
    exam; the Exam Builder loads the selection for review and saving."""
    pattern = _require_pattern(pattern_id, teacher)
    bank = get_question_bank(pattern.subject_id)
    usage = _usage_counts(pattern.subject_id)
    recent: set[str] = set()
    if request.avoid_recent_days:
        exams = [e for e in get_exam_store().list_by_subject(pattern.subject_id) if e.teacher_id == teacher.id]
        recent = recently_used_ids(exams, request.avoid_recent_days)

    def pool():
        return [q for q in bank.list() if q.id not in recent]

    result = assemble(pattern, pool(), usage_counts=usage)
    generated: list[GeneratedForGap] = []
    if not result.satisfied and request.generate_missing:
        generated = _fill_gaps(pattern, request.max_generate, exclude=recent)
        if any(g.question_id for g in generated):
            result = assemble(pattern, pool(), usage_counts=usage)
    return AssembleResponse(assembly=result, generated=generated, excluded_recent=len(recent & {q.id for q in bank.list()}))


class CheckRequest(BaseModel):
    question_ids: list[str]


@router.post("/{pattern_id}/check", response_model=ComplianceReport)
def check_against_pattern(
    pattern_id: str, request: CheckRequest, teacher: Teacher = Depends(get_current_teacher)
) -> ComplianceReport:
    """How well a hand-built question list matches the pattern (used by the
    Exam Builder's live compliance panel)."""
    pattern = _require_pattern(pattern_id, teacher)
    bank = get_question_bank(pattern.subject_id)
    questions = [q for qid in request.question_ids if (q := bank.get(qid)) is not None]
    return evaluate_selection(pattern, questions)
