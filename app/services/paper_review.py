"""Final-paper review operations: find replacements for a question, work out a
question's constraints for regeneration, and check what an edit does to
pattern compliance. All compliance judgements go through
pattern_assembly.evaluate_selection, the same check the assembler uses.
"""

from pydantic import BaseModel

from app.schemas.exam_pattern import ExamPattern
from app.schemas.question import Question, QuestionType
from app.schemas.bloom import BloomLevel
from app.schemas.skill import DifficultyBucket, difficulty_bucket
from app.services.pattern_assembly import ComplianceReport, evaluate_selection, question_unit
from app.services.question_usage import QuestionUsage


class QuestionConstraints(BaseModel):
    """What a replacement / regenerated question must keep so the paper's
    structure is unchanged."""

    question_type: QuestionType
    marks: int
    bloom_level: BloomLevel
    difficulty: DifficultyBucket
    topic_ids: list[str]
    unit: int | None  # pattern unit, when the pattern defines units
    section: str | None  # pattern section the question fills


class ConstraintCheck(BaseModel):
    name: str
    required: str
    actual: str
    ok: bool


class Candidate(BaseModel):
    question: Question
    matches: list[str]  # which of the original's properties it shares
    times_used: int
    last_used_at: str | None
    keeps_compliant: bool | None  # None when the exam has no pattern
    new_issues: list[str]  # compliance issues the swap would introduce


def _section_of(question_id: str, report: ComplianceReport | None) -> str | None:
    if report is None:
        return None
    return next((s.name for s in report.sections if question_id in s.question_ids), None)


def constraints_for(target: Question, paper: list[Question], pattern: ExamPattern | None) -> QuestionConstraints:
    report = evaluate_selection(pattern, paper) if pattern else None
    return QuestionConstraints(
        question_type=target.question_type,
        marks=target.marks,
        bloom_level=target.bloom_level,
        difficulty=difficulty_bucket(target.difficulty_score),
        topic_ids=list(target.topic_ids),
        unit=question_unit(target, pattern) if pattern else None,
        section=_section_of(target.id, report),
    )


def check_constraints(candidate: Question, c: QuestionConstraints, pattern: ExamPattern | None, topic_names: dict[str, str]) -> list[ConstraintCheck]:
    """Per-constraint comparison, shown to the teacher for a regenerated question."""
    name = lambda ids: ", ".join(topic_names.get(t, t) for t in ids) or "none"  # noqa: E731
    checks = [
        ConstraintCheck(name="Question type", required=c.question_type.value, actual=candidate.question_type.value,
                        ok=candidate.question_type == c.question_type),
        ConstraintCheck(name="Marks", required=str(c.marks), actual=str(candidate.marks), ok=candidate.marks == c.marks),
        ConstraintCheck(name="Bloom's level", required=c.bloom_level.name.title(), actual=candidate.bloom_level.name.title(),
                        ok=candidate.bloom_level == c.bloom_level),
        ConstraintCheck(name="Difficulty", required=c.difficulty, actual=difficulty_bucket(candidate.difficulty_score),
                        ok=difficulty_bucket(candidate.difficulty_score) == c.difficulty),
        ConstraintCheck(name="Topic", required=name(c.topic_ids), actual=name(candidate.topic_ids),
                        ok=not c.topic_ids or bool(set(c.topic_ids) & set(candidate.topic_ids))),
    ]
    if pattern is not None and c.unit is not None:
        actual_unit = question_unit(candidate, pattern)
        checks.append(ConstraintCheck(name="Unit", required=str(c.unit), actual=str(actual_unit), ok=actual_unit == c.unit))
    return checks


def _matches(q: Question, c: QuestionConstraints, pattern: ExamPattern | None) -> list[str]:
    m = []
    if q.question_type == c.question_type:
        m.append("type")
    if q.bloom_level == c.bloom_level:
        m.append("bloom")
    if difficulty_bucket(q.difficulty_score) == c.difficulty:
        m.append("difficulty")
    if set(q.topic_ids) & set(c.topic_ids):
        m.append("topic")
    if pattern is not None and c.unit is not None and question_unit(q, pattern) == c.unit:
        m.append("unit")
    return m


def find_reusable(
    target: Question,
    paper: list[Question],
    bank: list[Question],
    pattern: ExamPattern | None,
    usage: dict[str, QuestionUsage],
) -> Question | None:
    """A bank question satisfying *every* constraint of `target`, least used
    first - so regeneration costs no Gemini call when a good fit already exists."""
    c = constraints_for(target, paper, pattern)
    in_paper = {q.id for q in paper}
    required = {"type", "bloom", "difficulty"} | ({"topic"} if c.topic_ids else set()) | ({"unit"} if c.unit is not None else set())
    fits = [
        q for q in bank
        if q.id not in in_paper and q.marks == c.marks and required <= set(_matches(q, c, pattern))
    ]
    fits.sort(key=lambda q: (usage[q.id].times_used if q.id in usage else 0, str(usage[q.id].last_used_at) if q.id in usage else ""))
    return fits[0] if fits else None


def replacement_candidates(
    target: Question,
    paper: list[Question],
    bank: list[Question],
    pattern: ExamPattern | None,
    usage: dict[str, QuestionUsage],
    limit: int = 12,
) -> list[Candidate]:
    """Bank questions that could take `target`'s place. Same marks (so totals
    and section slots hold); ranked by how many of the original's properties
    they share, then least used. For pattern exams each candidate is checked
    against the full pattern so the teacher sees what a swap would break."""
    c = constraints_for(target, paper, pattern)
    in_paper = {q.id for q in paper}
    pool = [q for q in bank if q.id not in in_paper and q.marks == c.marks]
    scored = sorted(
        pool,
        key=lambda q: (
            -len(_matches(q, c, pattern)),
            usage[q.id].times_used if q.id in usage else 0,
        ),
    )[:limit]

    baseline = set(evaluate_selection(pattern, paper).issues) if pattern else set()
    out = []
    for q in scored:
        keeps, new_issues = None, []
        if pattern is not None:
            swapped = [q if p.id == target.id else p for p in paper]
            report = evaluate_selection(pattern, swapped)
            keeps = report.compliant
            new_issues = [i for i in report.issues if i not in baseline]
        u = usage.get(q.id)
        out.append(
            Candidate(
                question=q,
                matches=_matches(q, c, pattern),
                times_used=u.times_used if u else 0,
                last_used_at=u.last_used_at.isoformat() if u and u.last_used_at else None,
                keeps_compliant=keeps,
                new_issues=new_issues,
            )
        )
    # Compliance-preserving swaps first.
    out.sort(key=lambda cand: (cand.keeps_compliant is False, -len(cand.matches), cand.times_used))
    return out
