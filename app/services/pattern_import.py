"""Turn an uploaded question-paper pattern / scheme-of-examination document into
a draft ExamPattern the teacher reviews in the pattern form before saving.

The draft is deliberately *not* validated or saved here: documents are messy,
so we return whatever structure Gemini could extract plus human-readable
warnings, and the regular pattern form (with its validation) is the single
path by which a pattern gets stored.
"""

from typing import Literal

import httpx
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.graph_store import KnowledgeGraphStore, normalize_topic_name
from app.core.llm import get_genai_client
from app.schemas.bloom import BloomLevel
from app.schemas.exam_pattern import ExamPatternFields
from app.schemas.question import QuestionType
from app.services.document_extraction import extract_text

BloomLevelName = Literal["REMEMBER", "UNDERSTAND", "APPLY", "ANALYZE", "EVALUATE", "CREATE"]
MAX_DOCUMENT_WORDS = 12000

IMPORT_PROMPT = """You are reading an examination pattern / question-paper scheme document from a \
university. Extract the structure of ONE {exam_type_hint} question paper described in it.

Rules:
- exam_type: "MSE" for a mid-semester / internal / sessional exam, "SEE" for a semester-end / final exam.
- sections: one entry per part/section of the paper (e.g. Part A, Part B). num_questions is how many \
questions the paper contains in that section, marks_per_question the marks for each one. If the document \
says "answer any N of M", use N (the questions a student actually answers) and mention the choice in \
instructions.
- question_types: only from {question_types}. Map objective/multiple-choice to "mcq", fill-in-the-blanks to \
"fill_in_blank", programming questions to "code_fix" (fix/complete given code) or "code_write" (write the whole program), brief answers to "short_answer", essays/descriptive \
answers to "long_answer", problems with a numeric answer to "numerical". Leave empty if the document doesn't say.
- bloom_levels / bloom_distribution: only if the document states Bloom's / RBT levels (L1=REMEMBER, \
L2=UNDERSTAND, L3=APPLY, L4=ANALYZE, L5=EVALUATE, L6=CREATE). Percent is the share of total marks.
- difficulty_distribution: only if stated (easy/medium/hard, percent of marks).
- units: syllabus units/modules the paper covers, with the topic names listed for each unit and the \
percent of marks it carries (if stated).
- co_requirements: course outcomes the paper must cover, with the minimum number of questions if stated \
(use 1 if only listed).
- Do NOT invent numbers the document doesn't support. Put anything ambiguous or unmapped in `notes`.

DOCUMENT:
{text}"""


class _DraftSection(BaseModel):
    name: str
    instructions: str = ""
    num_questions: int
    marks_per_question: int
    question_types: list[QuestionType] = Field(default_factory=list)
    bloom_levels: list[BloomLevelName] = Field(default_factory=list)


class _DraftBloom(BaseModel):
    bloom_level: BloomLevelName
    percent: float


class _DraftDifficulty(BaseModel):
    difficulty: Literal["easy", "medium", "hard"]
    percent: float


class _DraftUnit(BaseModel):
    unit: int
    name: str = ""
    topic_names: list[str] = Field(default_factory=list)
    percent: float = 0


class _DraftCo(BaseModel):
    co_code: str
    min_questions: int = 1


class _PatternDraft(BaseModel):
    name: str
    exam_type: Literal["MSE", "SEE"]
    total_marks: int
    duration_minutes: int
    sections: list[_DraftSection] = Field(default_factory=list)
    bloom_distribution: list[_DraftBloom] = Field(default_factory=list)
    difficulty_distribution: list[_DraftDifficulty] = Field(default_factory=list)
    units: list[_DraftUnit] = Field(default_factory=list)
    co_requirements: list[_DraftCo] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PatternImportResult(BaseModel):
    draft: dict  # ExamPatternFields-shaped, possibly failing validation - the form shows the warnings
    warnings: list[str]
    source_filename: str
    valid: bool


@retry(
    retry=retry_if_exception_type((errors.ServerError, errors.APIError, httpx.TransportError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    reraise=True,
)
def _extract_draft(text: str, exam_type_hint: str) -> _PatternDraft | None:
    settings = get_settings()
    prompt = IMPORT_PROMPT.format(
        exam_type_hint=exam_type_hint,
        question_types=", ".join(f'"{t.value}"' for t in QuestionType),
        text=text,
    )
    response = get_genai_client().models.generate_content(
        model=settings.generation_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_PatternDraft),
    )
    return response.parsed


def _match_topics(names: list[str], graph_store: KnowledgeGraphStore) -> tuple[list[str], list[str]]:
    """Map topic names from the document onto this subject's knowledge-graph
    topics: exact normalized match first, then containment either way."""
    graph = graph_store.graph
    node_names = {nid: normalize_topic_name(graph.nodes[nid].get("name", nid)) for nid in graph.nodes}
    matched: list[str] = []
    unmatched: list[str] = []
    for name in names:
        norm = normalize_topic_name(name)
        if not norm:
            continue
        hit = norm if norm in graph else next(
            (nid for nid, nn in node_names.items() if nn and (norm in nn or nn in norm)), None
        )
        if hit:
            if hit not in matched:
                matched.append(hit)
        else:
            unmatched.append(name)
    return matched, unmatched


def import_pattern(path: str, filename: str, graph_store: KnowledgeGraphStore, exam_type_hint: str = "") -> PatternImportResult:
    text = extract_text(path)
    words = text.split()
    if not words:
        raise ValueError("No readable text found in the document")
    warnings: list[str] = []
    if len(words) > MAX_DOCUMENT_WORDS:
        warnings.append(f"Document is long; only the first {MAX_DOCUMENT_WORDS} words were read.")
        text = " ".join(words[:MAX_DOCUMENT_WORDS])

    parsed = _extract_draft(text, exam_type_hint or "MSE or SEE")
    if parsed is None:
        raise ValueError("Couldn't extract a pattern from this document")

    units = []
    for unit in parsed.units:
        topic_ids, unmatched = _match_topics(unit.topic_names, graph_store)
        if unmatched:
            warnings.append(
                f"Unit {unit.unit}: no knowledge-graph topic matched {', '.join(unmatched[:5])}"
                f"{'...' if len(unmatched) > 5 else ''} - upload that unit's material or pick topics manually."
            )
        units.append({"unit": unit.unit, "name": unit.name, "topic_ids": topic_ids, "percent": unit.percent})

    draft = {
        "name": parsed.name,
        "exam_type": parsed.exam_type,
        "description": "",  # the pattern keeps source_filename; the list shows where it came from
        "total_marks": parsed.total_marks,
        "duration_minutes": parsed.duration_minutes,
        "sections": [
            {
                "name": s.name,
                "instructions": s.instructions,
                "num_questions": s.num_questions,
                "marks_per_question": s.marks_per_question,
                "question_types": [t.value for t in s.question_types],
                "bloom_levels": [int(BloomLevel[b]) for b in s.bloom_levels],
            }
            for s in parsed.sections
        ],
        "bloom_distribution": [
            {"bloom_level": int(BloomLevel[b.bloom_level]), "percent": b.percent} for b in parsed.bloom_distribution
        ],
        "difficulty_distribution": [d.model_dump() for d in parsed.difficulty_distribution],
        "units": units,
        "co_requirements": [c.model_dump() for c in parsed.co_requirements],
        "tolerance_percent": 10.0,
    }
    warnings.extend(parsed.notes)

    valid = True
    try:
        ExamPatternFields.model_validate(draft)
    except ValidationError as exc:
        valid = False
        warnings.extend(err["msg"].removeprefix("Value error, ") for err in exc.errors())

    return PatternImportResult(draft=draft, warnings=warnings, source_filename=filename, valid=valid)
