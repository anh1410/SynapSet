"""Final-paper review for teachers: blueprint, replacement candidates,
constraint-preserving regeneration, marks edits, and PDF exports.

Review operations take the *draft* question list the teacher is editing
(`question_ids`) so compliance can be judged before anything is saved; the
paper itself is saved through the existing PATCH /exams/{id}.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_current_teacher
from app.core import clock
from app.core.config import get_settings
from app.core.exam_store import get_exam_store
from app.core.graph_store import course_outcome_node_ids, get_graph_store
from app.core.pattern_store import get_pattern_store
from app.core.question_bank import get_question_bank
from app.core.subject_store import get_subject_store
from app.core.submission_store import get_submission_store
from app.schemas.exam import Exam
from app.schemas.exam_pattern import ExamPattern
from app.schemas.question import Question
from app.schemas.skill import difficulty_bucket
from app.schemas.teacher import Teacher
from app.services.blueprint import Blueprint, describe_paper
from app.services.difficulty_scoring import score_difficulty
from app.services.duplicate_detection import find_duplicates
from app.services.paper_export import render_answer_key, render_blueprint, render_paper
from app.services.paper_review import (
    Candidate,
    ConstraintCheck,
    check_constraints,
    constraints_for,
    find_reusable,
    replacement_candidates,
)
from app.services.question_generation import generate_questions
from app.services.question_usage import usage_by_question

router = APIRouter(prefix="/api/v1/exams", tags=["paper review"], dependencies=[Depends(get_current_teacher)])


def _owned_exam(exam_id: str, teacher: Teacher) -> Exam:
    exam = get_exam_store().get(exam_id)
    if exam is None or exam.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


def _pattern(exam: Exam) -> ExamPattern | None:
    return get_pattern_store().get(exam.pattern_id) if exam.pattern_id else None


def _paper(exam: Exam, question_ids: list[str] | None, marks_overrides: dict[str, int] | None = None) -> list[Question]:
    """The draft paper: questions in the given order, all from this exam's subject
    bank, with any unsaved marks edits applied (the bank itself is untouched)."""
    bank = get_question_bank(exam.subject_id)
    ids = exam.question_ids if question_ids is None else question_ids
    missing = [qid for qid in ids if bank.get(qid) is None]
    if question_ids is not None and missing:
        raise HTTPException(status_code=422, detail=f"Unknown question(s) for this subject: {', '.join(missing[:5])}")
    overrides = marks_overrides or {}
    if any(not 1 <= m <= 100 for m in overrides.values()):
        raise HTTPException(status_code=422, detail="Marks must be between 1 and 100")
    paper = []
    for qid in ids:
        q = bank.get(qid)
        if q is None:
            continue
        paper.append(q.model_copy(update={"marks": overrides[qid]}) if qid in overrides else q)
    return paper


def _topic_names(subject_id: str) -> dict[str, str]:
    graph = get_graph_store(subject_id).graph
    return {nid: data.get("name", nid) for nid, data in graph.nodes(data=True)}


def _describe(exam: Exam, paper: list[Question]) -> Blueprint:
    cos = course_outcome_node_ids(get_graph_store(exam.subject_id).graph)
    return describe_paper(exam, paper, _pattern(exam), _topic_names(exam.subject_id), cos)


def _usage(exam: Exam, bank: list[Question]):
    settings = get_settings()
    exams = get_exam_store().list_by_subject(exam.subject_id)
    subs = [s for e in exams for s in get_submission_store().list_by_exam(e.id)]
    return usage_by_question([q.id for q in bank], exams, subs, settings.recent_use_days, settings.frequent_use_count)


def _require_editable(exam: Exam) -> None:
    if get_submission_store().list_by_exam(exam.id):
        raise HTTPException(
            status_code=409,
            detail="Students have already submitted this exam, so its paper is locked. Duplicate it to make a new version.",
        )


class DraftRequest(BaseModel):
    question_ids: list[str] | None = None  # None = the saved paper
    # Unsaved marks edits (question id -> marks), applied to the draft only.
    marks_overrides: dict[str, int] = {}


@router.post("/{exam_id}/blueprint", response_model=Blueprint)
def blueprint(exam_id: str, request: DraftRequest, teacher: Teacher = Depends(get_current_teacher)) -> Blueprint:
    """Target-vs-actual distributions and compliance for the saved or draft paper."""
    exam = _owned_exam(exam_id, teacher)
    return _describe(exam, _paper(exam, request.question_ids, request.marks_overrides))


class TargetRequest(DraftRequest):
    target_id: str


def _target(paper: list[Question], target_id: str) -> Question:
    target = next((q for q in paper if q.id == target_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="That question isn't in this paper")
    return target


@router.post("/{exam_id}/review/candidates", response_model=list[Candidate])
def candidates(exam_id: str, request: TargetRequest, teacher: Teacher = Depends(get_current_teacher)) -> list[Candidate]:
    """Bank questions that could replace one question, each with what the swap
    would do to pattern compliance."""
    exam = _owned_exam(exam_id, teacher)
    paper = _paper(exam, request.question_ids, request.marks_overrides)
    target = _target(paper, request.target_id)
    bank = get_question_bank(exam.subject_id).list()
    return replacement_candidates(target, paper, bank, _pattern(exam), _usage(exam, bank))


class RegenerateRequest(TargetRequest):
    # Skip reuse and always ask the generator for a fresh question.
    force_new: bool = False


class RegenerateResult(BaseModel):
    question: Question
    source: Literal["reused", "generated"]
    checks: list[ConstraintCheck]
    all_constraints_met: bool
    note: str


@router.post("/{exam_id}/review/regenerate", response_model=RegenerateResult)
def regenerate(exam_id: str, request: RegenerateRequest, teacher: Teacher = Depends(get_current_teacher)) -> RegenerateResult:
    """Replacement for one question that keeps its constraints (type, marks,
    Bloom's level, difficulty band, topic and pattern unit). An existing bank
    question that meets all of them is reused first - no Gemini call. Otherwise
    the Graph-RAG generator writes one (a second try if the first misses the
    difficulty band), which is saved to the bank. The paper itself isn't
    changed until the teacher saves it."""
    exam = _owned_exam(exam_id, teacher)
    _require_editable(exam)
    paper = _paper(exam, request.question_ids, request.marks_overrides)
    target = _target(paper, request.target_id)
    pattern = _pattern(exam)
    bank_store = get_question_bank(exam.subject_id)
    bank = bank_store.list()
    names = _topic_names(exam.subject_id)
    c = constraints_for(target, paper, pattern)

    if not request.force_new:
        reused = find_reusable(target, paper, bank, pattern, _usage(exam, bank))
        if reused is not None:
            checks = check_constraints(reused, c, pattern, names)
            return RegenerateResult(
                question=reused, source="reused", checks=checks, all_constraints_met=all(x.ok for x in checks),
                note="An existing bank question already meets every constraint, so no new question was generated.",
            )

    topic = next((names[t] for t in c.topic_ids if t in names), None) or (
        target.provenance.requested_topic if target.provenance else None
    )
    if not topic:
        raise HTTPException(status_code=422, detail="This question has no knowledge-graph topic to generate from.")

    graph_store = get_graph_store(exam.subject_id)
    best: Question | None = None
    best_rank = (-1, -1)
    for _ in range(2):  # at most one retry, to bound Gemini calls
        try:
            drafts = generate_questions(
                topic=topic, graph_store=graph_store, subject_id=exam.subject_id, num_questions=1,
                bloom_level=c.bloom_level, marks=c.marks, question_type=c.question_type,
                scenario_based=target.scenario_based,  # keep an interview-style question interview-style
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Question generation failed ({type(exc).__name__})") from exc
        if not drafts:
            continue
        q = drafts[0]
        # Pin the structural constraints; the generator is asked for them but not trusted.
        q.marks, q.bloom_level, q.unit = c.marks, c.bloom_level, c.unit
        for t in c.topic_ids[:1]:
            if t not in q.topic_ids:
                q.topic_ids.insert(0, t)
        if not q.co_ids:
            q.co_ids = list(target.co_ids)  # same topic, same course outcome mapping
        q.difficulty_score = score_difficulty(q, graph_store).score
        # Prefer a question that is actually different from the one being replaced,
        # then one in the right difficulty band; spend the retry on whichever is missing.
        rephrase = any(m.is_duplicate for m in find_duplicates(q, [target]))
        rank = (int(not rephrase), int(difficulty_bucket(q.difficulty_score) == c.difficulty))
        if rank > best_rank:
            best, best_rank = q, rank
        if best_rank == (1, 1):
            break
    if best is None:
        raise HTTPException(status_code=502, detail="The generator didn't return a usable question - try again.")

    dupes = [m for m in find_duplicates(best, bank) if m.is_duplicate]
    bank_store.add(best)
    checks = check_constraints(best, c, pattern, names)
    note = "Generated from the course material for this topic."
    if not all(x.ok for x in checks):
        note = "Generated, but it doesn't meet every constraint (see below) - review before using it."
    if best_rank[0] == 0:
        note += " It is very similar to the question it would replace - try again for a more different one."
    elif dupes:
        note += " It closely resembles another bank question."
    return RegenerateResult(question=best, source="generated", checks=checks,
                            all_constraints_met=all(x.ok for x in checks), note=note)


class MarksRequest(TargetRequest):
    marks: int


class MarksResult(BaseModel):
    question: Question
    copied: bool  # True = a copy was made so other exams using the original are unaffected


@router.post("/{exam_id}/review/marks", response_model=MarksResult)
def set_marks(exam_id: str, request: MarksRequest, teacher: Teacher = Depends(get_current_teacher)) -> MarksResult:
    """Change one question's marks for this paper. If the question is used by
    another exam or already has graded answers, a copy is made instead so
    those aren't affected."""
    exam = _owned_exam(exam_id, teacher)
    _require_editable(exam)
    if not 1 <= request.marks <= 100:
        raise HTTPException(status_code=422, detail="Marks must be between 1 and 100")
    paper = _paper(exam, request.question_ids)
    target = _target(paper, request.target_id)
    bank_store = get_question_bank(exam.subject_id)
    usage = _usage(exam, bank_store.list()).get(target.id)
    elsewhere = usage is not None and (any(u.exam_id != exam.id for u in usage.exams) or usage.responses > 0)
    if elsewhere:
        copy = target.model_copy(update={
            "id": str(uuid.uuid4()), "marks": request.marks, "derived_from": target.id, "created_at": clock.utcnow(),
        })
        bank_store.add(copy)
        return MarksResult(question=copy, copied=True)
    target.marks = request.marks
    bank_store.add(target)
    return MarksResult(question=target, copied=False)


@router.get("/{exam_id}/export/{kind}")
def export_pdf(
    exam_id: str,
    kind: Literal["paper", "answer-key", "blueprint"],
    tz_offset: int = Query(0, description="Minutes, as reported by JavaScript's Date.getTimezoneOffset()"),
    teacher: Teacher = Depends(get_current_teacher),
) -> Response:
    exam = _owned_exam(exam_id, teacher)
    paper = _paper(exam, None)
    if not paper:
        raise HTTPException(status_code=422, detail="This exam has no questions to export")
    pattern = _pattern(exam)
    bp = _describe(exam, paper)
    subject = get_subject_store().get(exam.subject_id)
    subject_name = subject.name if subject else "Subject"
    if kind == "paper":
        data = render_paper(exam, paper, bp, pattern, subject_name, teacher.name, tz_offset)
    elif kind == "answer-key":
        data = render_answer_key(exam, paper, bp, pattern, subject_name, teacher.name, tz_offset)
    else:
        data = render_blueprint(exam, bp, subject_name, teacher.name, tz_offset)
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in exam.name).strip().replace(" ", "_")[:60] or "exam"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}_{kind}.pdf"'},
    )
