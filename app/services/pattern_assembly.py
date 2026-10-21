"""Constraint-based assessment assembly against an MSE/SEE question paper pattern.

This is the successor of the CP-SAT paper optimizer that was removed in commit
372fc2e. It's the same 0/1 selection model - one boolean per (question, section)
pair, hard section/marks constraints, tolerance bands on the Bloom's /
difficulty / unit mark distributions, minimum course-outcome coverage, and an
objective that maximizes distinct knowledge-graph topics covered - but solved
with scipy's MILP solver (HiGHS), which ships with the already-pinned scipy, so
it needs no extra dependency. CP-SAT is overkill for problems this size.

`evaluate_selection` reuses the same model to check an arbitrary hand-picked
list of questions against a pattern, so the Exam Builder's live compliance
panel and the assembler can never disagree about what "compliant" means.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from pydantic import BaseModel
from scipy.optimize import Bounds, LinearConstraint, milp

from app.schemas.bloom import BloomLevel
from app.schemas.exam_pattern import ExamPatternFields, PatternSection
from app.schemas.question import Question, QuestionType
from app.schemas.skill import difficulty_bucket

ConstraintFamily = Literal["sections", "bloom", "difficulty", "units", "course_outcomes"]
DISTRIBUTION_FAMILIES: tuple[ConstraintFamily, ...] = ("bloom", "difficulty", "units", "course_outcomes")

_BLOOM_LABELS = {b.value: b.name.title() for b in BloomLevel}
_TYPE_LABELS = {
    "mcq": "Multiple Choice",
    "fill_in_blank": "Fill in the Blank",
    "short_answer": "Short Answer",
    "long_answer": "Long Answer",
    "numerical": "Numerical",
    "code_fix": "Coding (Fix the Code)",
    "code_write": "Coding (Write the Program)",
}
_SKILL_LABELS = {"conceptual": "Conceptual", "reasoning": "Reasoning", "coding": "Coding"}
_DIFFICULTY_LABELS = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


# ---------- report models (returned by the API) ----------


class SectionReport(BaseModel):
    name: str
    required: int
    marks_per_question: int
    filled: int
    question_ids: list[str]
    eligible_in_pool: int  # how many candidate questions could fill this section at all


class DistributionRow(BaseModel):
    key: str
    label: str
    target_percent: float | None  # None = no target set (reported for information only)
    actual_percent: float
    actual_marks: float  # whole numbers except topic rows, where multi-topic questions split their marks
    within_tolerance: bool


class CoRow(BaseModel):
    co_code: str
    min_questions: int
    min_percent: float | None = None
    actual: int  # questions tagged with this CO
    actual_marks: int = 0
    actual_percent: float = 0.0  # share of the pattern's total marks
    met: bool


class ComplianceReport(BaseModel):
    compliant: bool
    target_marks: int
    actual_marks: int
    sections: list[SectionReport]
    bloom: list[DistributionRow]
    difficulty: list[DistributionRow]
    units: list[DistributionRow]
    course_outcomes: list[CoRow]
    # Informational distributions (patterns don't target these), shown in the blueprint.
    question_types: list[DistributionRow] = []
    skills: list[DistributionRow] = []
    topics_covered: int
    unassigned_question_ids: list[str]
    issues: list[str]


# ---------- helpers ----------


def question_unit(question: Question, pattern: ExamPatternFields) -> int | None:
    """Which of the pattern's units a question belongs to: its explicit unit tag
    if that's one of the pattern's units, else the first unit sharing a topic."""
    if not pattern.units:
        return None
    unit_numbers = {u.unit for u in pattern.units}
    if question.unit is not None and question.unit in unit_numbers:
        return question.unit
    topics = set(question.topic_ids)
    for unit in pattern.units:
        if topics & set(unit.topic_ids):
            return unit.unit
    return None


def is_eligible(question: Question, section: PatternSection, pattern: ExamPatternFields) -> bool:
    if question.marks != section.marks_per_question:
        return False
    if section.question_types and question.question_type not in section.question_types:
        return False
    if section.bloom_levels and question.bloom_level not in section.bloom_levels:
        return False
    if pattern.units and question_unit(question, pattern) is None:
        return False
    return True


def _band(pattern: ExamPatternFields, percent: float) -> tuple[float, float]:
    total = pattern.total_marks
    tol = pattern.tolerance_percent
    return max(0.0, total * (percent - tol) / 100), total * (percent + tol) / 100


def _family_keys(pattern: ExamPatternFields, family: ConstraintFamily) -> dict[str, float]:
    """Target percent per key for a distribution family; keys absent from a
    non-empty distribution get a 0% target (i.e. at most the tolerance)."""
    if family == "bloom" and pattern.bloom_distribution:
        targets = {str(int(b.bloom_level)): b.percent for b in pattern.bloom_distribution}
        return {str(b.value): targets.get(str(b.value), 0.0) for b in BloomLevel}
    if family == "difficulty" and pattern.difficulty_distribution:
        targets = {d.difficulty: d.percent for d in pattern.difficulty_distribution}
        return {k: targets.get(k, 0.0) for k in ("easy", "medium", "hard")}
    if family == "units" and pattern.units:
        return {str(u.unit): u.percent for u in pattern.units}
    return {}


def _family_key(question: Question, family: ConstraintFamily, pattern: ExamPatternFields) -> str | None:
    if family == "bloom":
        return str(int(question.bloom_level))
    if family == "difficulty":
        return difficulty_bucket(question.difficulty_score)
    if family == "units":
        unit = question_unit(question, pattern)
        return str(unit) if unit is not None else None
    return None


# ---------- MILP model ----------


@dataclass
class _Model:
    pattern: ExamPatternFields
    questions: list[Question]
    pairs: list[tuple[int, int]]  # (question index, section index)
    topics: list[str]
    rows: list[np.ndarray] = field(default_factory=list)
    lbs: list[float] = field(default_factory=list)
    ubs: list[float] = field(default_factory=list)

    @property
    def n_x(self) -> int:
        return len(self.pairs)

    @property
    def n_vars(self) -> int:
        return self.n_x + len(self.topics)

    def add_row(self, coeffs: dict[int, float], lb: float, ub: float) -> None:
        row = np.zeros(self.n_vars)
        for idx, val in coeffs.items():
            row[idx] += val
        self.rows.append(row)
        self.lbs.append(lb)
        self.ubs.append(ub)


def _build_model(pattern: ExamPatternFields, questions: list[Question]) -> _Model:
    pairs = [
        (qi, si)
        for qi, q in enumerate(questions)
        for si, section in enumerate(pattern.sections)
        if is_eligible(q, section, pattern)
    ]
    topics = sorted({t for qi, _ in pairs for t in questions[qi].topic_ids})
    return _Model(pattern=pattern, questions=questions, pairs=pairs, topics=topics)


def _add_structure(model: _Model, *, exact_sections: bool) -> None:
    """Each question used at most once; each section gets exactly (or at most)
    its required number of questions; topic-coverage indicators are bounded by
    the selections that cover them."""
    by_question: dict[int, dict[int, float]] = {}
    by_section: dict[int, dict[int, float]] = {}
    for p, (qi, si) in enumerate(model.pairs):
        by_question.setdefault(qi, {})[p] = 1
        by_section.setdefault(si, {})[p] = 1
    for coeffs in by_question.values():
        model.add_row(coeffs, 0, 1)
    for si, section in enumerate(model.pattern.sections):
        coeffs = by_section.get(si, {})
        model.add_row(coeffs, section.num_questions if exact_sections else 0, section.num_questions)

    topic_index = {t: model.n_x + k for k, t in enumerate(model.topics)}
    for t, t_idx in topic_index.items():
        coeffs = {t_idx: 1.0}
        for p, (qi, _) in enumerate(model.pairs):
            if t in model.questions[qi].topic_ids:
                coeffs[p] = -1.0
        model.add_row(coeffs, -np.inf, 0)  # covered_t <= sum of selections covering t


def _add_family(model: _Model, family: ConstraintFamily) -> None:
    pattern = model.pattern
    if family == "course_outcomes":
        for req in pattern.co_requirements:
            tagged = [(p, model.questions[qi]) for p, (qi, _) in enumerate(model.pairs) if req.co_code in model.questions[qi].co_ids]
            if req.min_questions:
                model.add_row({p: 1.0 for p, _ in tagged}, req.min_questions, np.inf)
            if req.min_percent:
                model.add_row({p: float(q.marks) for p, q in tagged}, pattern.total_marks * req.min_percent / 100, np.inf)
        return
    for key, percent in _family_keys(pattern, family).items():
        lo, hi = _band(pattern, percent)
        coeffs = {
            p: float(model.questions[qi].marks)
            for p, (qi, _) in enumerate(model.pairs)
            if _family_key(model.questions[qi], family, pattern) == key
        }
        model.add_row(coeffs, lo, hi)


def _solve(
    model: _Model,
    *,
    usage_counts: dict[str, int] | None = None,
    maximize_fill: bool = False,
    time_limit: float = 10.0,
    extra_costs: dict[str, float] | None = None,
) -> tuple[str, list[tuple[int, int]]]:
    if model.n_x == 0:
        return "infeasible", []

    c = np.zeros(model.n_vars)
    c[model.n_x :] = -1.0  # maximize distinct topics covered
    usage_counts = usage_counts or {}
    extra_costs = extra_costs or {}
    for p, (qi, _) in enumerate(model.pairs):
        qid = model.questions[qi].id
        # Mild preference for questions not already used in other exams, so
        # repeated assembly doesn't hand out the same paper every time.
        c[p] += 0.05 * usage_counts.get(qid, 0) + extra_costs.get(qid, 0.0)
        if maximize_fill:
            c[p] -= 100.0

    integrality = np.zeros(model.n_vars)
    integrality[: model.n_x] = 1
    constraints = (
        [LinearConstraint(np.vstack(model.rows), np.array(model.lbs), np.array(model.ubs))] if model.rows else []
    )
    res = milp(
        c,
        constraints=constraints,
        integrality=integrality,
        bounds=Bounds(0, 1),
        options={"time_limit": time_limit, "disp": False},
    )
    if res.x is None:
        return "infeasible", []
    status = "optimal" if res.status == 0 else "feasible"
    chosen = [model.pairs[p] for p in range(model.n_x) if res.x[p] > 0.5]
    return status, chosen


def _feasible_with(
    pattern: ExamPatternFields, questions: list[Question], families: tuple[ConstraintFamily, ...]
) -> bool:
    model = _build_model(pattern, questions)
    _add_structure(model, exact_sections=True)
    for family in families:
        _add_family(model, family)
    status, _ = _solve(model, time_limit=5.0)
    return status != "infeasible"


# ---------- reporting ----------


def info_distribution(selected: list[Question], total_marks: int, key, labels: dict[str, str]) -> list[DistributionRow]:
    """Share of marks per key, for distributions a pattern doesn't target."""
    marks: Counter[str] = Counter()
    for q in selected:
        marks[key(q)] += q.marks
    order = [k for k in labels if k in marks] + sorted(k for k in marks if k not in labels)
    return [
        DistributionRow(
            key=k,
            label=labels.get(k, k),
            target_percent=None,
            actual_percent=round(100 * marks[k] / total_marks, 1) if total_marks else 0.0,
            actual_marks=marks[k],
            within_tolerance=True,
        )
        for k in order
    ]


def _distribution_rows(
    pattern: ExamPatternFields,
    selected: list[Question],
    family: ConstraintFamily,
    labels: dict[str, str],
) -> list[DistributionRow]:
    targets = _family_keys(pattern, family)
    marks_by_key: Counter[str] = Counter()
    for q in selected:
        key = _family_key(q, family, pattern)
        if key is not None:
            marks_by_key[key] += q.marks
    total = pattern.total_marks
    keys = list(targets) or [k for k in labels if k in marks_by_key]
    rows = []
    for key in keys:
        marks = marks_by_key.get(key, 0)
        target = targets.get(key) if targets else None
        if target is not None:
            lo, hi = _band(pattern, target)
            ok = lo - 1e-6 <= marks <= hi + 1e-6
        else:
            ok = True
        if target == 0 and marks == 0:
            continue  # untargeted and unused - noise
        rows.append(
            DistributionRow(
                key=key,
                label=labels.get(key, key),
                target_percent=target,
                actual_percent=round(100 * marks / total, 1) if total else 0.0,
                actual_marks=marks,
                within_tolerance=ok,
            )
        )
    return rows


def build_report(
    pattern: ExamPatternFields,
    assignment: list[tuple[Question, int]],
    unassigned: list[Question],
    eligible_counts: list[int],
) -> ComplianceReport:
    selected = [q for q, _ in assignment]
    sections = []
    issues: list[str] = []
    sections_short = False
    for si, section in enumerate(pattern.sections):
        ids = [q.id for q, s in assignment if s == si]
        sections.append(
            SectionReport(
                name=section.name,
                required=section.num_questions,
                marks_per_question=section.marks_per_question,
                filled=len(ids),
                question_ids=ids,
                eligible_in_pool=eligible_counts[si],
            )
        )
        if len(ids) < section.num_questions:
            sections_short = True
            issues.append(
                f"{section.name}: {len(ids)} of {section.num_questions} "
                f"{section.marks_per_question}-mark question(s) filled"
            )

    unit_labels = {str(u.unit): (u.name or f"Unit {u.unit}") for u in pattern.units}
    bloom = _distribution_rows(pattern, selected, "bloom", {str(k): v for k, v in _BLOOM_LABELS.items()})
    difficulty = _distribution_rows(pattern, selected, "difficulty", _DIFFICULTY_LABELS)
    units = _distribution_rows(pattern, selected, "units", unit_labels) if pattern.units else []
    for label, rows in (("Bloom's", bloom), ("Difficulty", difficulty), ("Unit", units)):
        for row in rows:
            if not row.within_tolerance:
                issues.append(
                    f"{label} '{row.label}' is {row.actual_percent:g}% of marks "
                    f"(target {row.target_percent:g}% +/- {pattern.tolerance_percent:g}%)"
                )

    co_rows = []
    total = pattern.total_marks
    for req in pattern.co_requirements:
        tagged = [q for q in selected if req.co_code in q.co_ids]
        marks = sum(q.marks for q in tagged)
        percent = round(100 * marks / total, 1) if total else 0.0
        count_ok = len(tagged) >= req.min_questions
        percent_ok = req.min_percent is None or percent + 1e-6 >= req.min_percent
        co_rows.append(
            CoRow(
                co_code=req.co_code,
                min_questions=req.min_questions,
                min_percent=req.min_percent,
                actual=len(tagged),
                actual_marks=marks,
                actual_percent=percent,
                met=count_ok and percent_ok,
            )
        )
        if not count_ok:
            issues.append(f"{req.co_code}: {len(tagged)} of at least {req.min_questions} question(s)")
        if not percent_ok:
            issues.append(f"{req.co_code}: {percent:g}% of marks, needs at least {req.min_percent:g}%")

    if unassigned:
        issues.append(f"{len(unassigned)} question(s) don't fit any open section slot in this pattern")

    actual_marks = sum(q.marks for q in selected)
    if actual_marks != pattern.total_marks and not sections_short:
        issues.append(f"Total is {actual_marks} marks, pattern requires {pattern.total_marks}")

    return ComplianceReport(
        compliant=not issues,
        target_marks=pattern.total_marks,
        actual_marks=actual_marks,
        sections=sections,
        bloom=bloom,
        difficulty=difficulty,
        units=units,
        course_outcomes=co_rows,
        question_types=info_distribution(selected, total, lambda q: q.question_type.value, _TYPE_LABELS),
        skills=info_distribution(selected, total, lambda q: q.effective_skill_category.value, _SKILL_LABELS),
        topics_covered=len({t for q in selected for t in q.topic_ids}),
        unassigned_question_ids=[q.id for q in unassigned],
        issues=issues,
    )


def _eligible_counts(pattern: ExamPatternFields, questions: list[Question]) -> list[int]:
    return [sum(1 for q in questions if is_eligible(q, s, pattern)) for s in pattern.sections]


def _ordered_assignment(questions: list[Question], chosen: list[tuple[int, int]]) -> list[tuple[Question, int]]:
    assignment = [(questions[qi], si) for qi, si in chosen]
    assignment.sort(key=lambda pair: (pair[1], int(pair[0].bloom_level), pair[0].id))
    return assignment


# ---------- public API ----------


class AssemblyResult(BaseModel):
    status: Literal["optimal", "feasible", "infeasible"]
    # True when every pattern constraint is met. When False, `question_ids`
    # is a best-effort draft (see `relaxed`) the teacher can finish by hand.
    satisfied: bool
    relaxed: list[ConstraintFamily]  # constraint families dropped to produce the draft
    blocking: list[ConstraintFamily]  # families that individually make the bank infeasible
    question_ids: list[str]
    report: ComplianceReport


def assemble(
    pattern: ExamPatternFields,
    candidates: list[Question],
    *,
    usage_counts: dict[str, int] | None = None,
    time_limit: float = 10.0,
) -> AssemblyResult:
    eligible_counts = _eligible_counts(pattern, candidates)

    model = _build_model(pattern, candidates)
    _add_structure(model, exact_sections=True)
    for family in DISTRIBUTION_FAMILIES:
        _add_family(model, family)
    status, chosen = _solve(model, usage_counts=usage_counts, time_limit=time_limit)

    relaxed: list[ConstraintFamily] = []
    blocking: list[ConstraintFamily] = []
    if status == "infeasible":
        # Work out *why*, then hand back the best draft we can.
        if not _feasible_with(pattern, candidates, ()):
            blocking = ["sections"]
            relaxed = ["sections", *DISTRIBUTION_FAMILIES]
            draft = _build_model(pattern, candidates)
            _add_structure(draft, exact_sections=False)
            _, chosen = _solve(draft, usage_counts=usage_counts, maximize_fill=True, time_limit=time_limit)
        else:
            blocking = [f for f in DISTRIBUTION_FAMILIES if not _feasible_with(pattern, candidates, (f,))]
            keep = tuple(f for f in DISTRIBUTION_FAMILIES if f not in blocking)
            relaxed = list(blocking) if _feasible_with(pattern, candidates, keep) else list(DISTRIBUTION_FAMILIES)
            if not blocking:  # only jointly infeasible
                blocking = list(relaxed)
            draft = _build_model(pattern, candidates)
            _add_structure(draft, exact_sections=True)
            for family in DISTRIBUTION_FAMILIES:
                if family not in relaxed:
                    _add_family(draft, family)
            _, chosen = _solve(draft, usage_counts=usage_counts, time_limit=time_limit)

    assignment = _ordered_assignment(candidates, chosen)
    report = build_report(pattern, assignment, [], eligible_counts)
    return AssemblyResult(
        status=status,
        satisfied=status != "infeasible" and report.compliant,
        relaxed=relaxed,
        blocking=blocking,
        question_ids=[q.id for q, _ in assignment],
        report=report,
    )


def evaluate_selection(pattern: ExamPatternFields, selected: list[Question]) -> ComplianceReport:
    """Check a hand-picked question list against the pattern: fit as many of
    the questions as possible into section slots (same eligibility rules as
    the assembler), then report on the resulting paper."""
    model = _build_model(pattern, selected)
    _add_structure(model, exact_sections=False)
    _, chosen = _solve(model, maximize_fill=True, time_limit=5.0)
    assignment = _ordered_assignment(selected, chosen)
    assigned_ids = {q.id for q, _ in assignment}
    unassigned = [q for q in selected if q.id not in assigned_ids]
    return build_report(pattern, assignment, unassigned, _eligible_counts(pattern, selected))


# ---------- gap filling (Graph-RAG generation) ----------


class GapRequest(BaseModel):
    """One question the generator should write so the pattern becomes satisfiable."""

    section: str
    topic_id: str
    topic_name: str
    question_type: QuestionType
    bloom_level: BloomLevel
    marks: int
    unit: int | None = None  # pin the generated question to this pattern unit


@dataclass
class TopicInfo:
    id: str
    name: str
    importance: float
    question_count: int


_VIRTUAL_PREFIX = "__virtual__"
_VIRTUAL_COST = 10.0  # >> topic-coverage reward, so the solver generates as little as possible
_DIFFICULTY_PROBES = (3.0, 6.0, 8.5)  # one representative score per easy/medium/hard bucket


def plan_gap_requests(
    pattern: ExamPatternFields,
    candidates: list[Question],
    topics: list[TopicInfo],
    max_questions: int,
) -> list[GapRequest]:
    """Decide exactly which questions to generate so the whole pattern becomes
    satisfiable - not just the section counts, but the Bloom's / difficulty /
    unit distributions and CO minimums too.

    It reuses the assembly model: alongside the real bank questions it adds
    hypothetical "virtual" questions for every (section, allowed Bloom's level,
    unit, difficulty) combination, each carrying a high cost. The solver then
    picks the cheapest paper, i.e. the one that keeps as many real questions as
    possible and generates only the virtual slots it can't avoid. Each chosen
    virtual slot becomes a generation request; its topic comes from its unit,
    least-covered and most important first, so new questions also push
    coverage toward neglected topics.
    """
    if not topics:
        return []
    topics_by_id = {t.id: t for t in topics}
    by_coverage = sorted(topics, key=lambda t: (t.question_count, -t.importance))

    # Topic pool per unit (or one pool of all topics when the pattern has no units).
    if pattern.units:
        unit_pools: dict[int | None, list[TopicInfo]] = {
            u.unit: sorted(
                (topics_by_id[t] for t in dict.fromkeys(u.topic_ids) if t in topics_by_id),
                key=lambda t: (t.question_count, -t.importance),
            )
            for u in pattern.units
        }
        unit_pools = {u: pool for u, pool in unit_pools.items() if pool}
    else:
        unit_pools = {None: by_coverage}
    if not unit_pools:
        return []

    difficulties = _DIFFICULTY_PROBES if pattern.difficulty_distribution else (None,)
    virtual: list[Question] = []
    meta: dict[str, tuple[int, BloomLevel, int | None]] = {}
    for si, section in enumerate(pattern.sections):
        qtype = (section.question_types or [QuestionType.SHORT_ANSWER])[0]
        levels = section.bloom_levels or list(BloomLevel)
        for level in levels:
            for unit, pool in unit_pools.items():
                for difficulty in difficulties:
                    for k in range(section.num_questions):
                        vid = f"{_VIRTUAL_PREFIX}{si}_{int(level)}_{unit}_{difficulty}_{k}"
                        virtual.append(
                            Question(
                                id=vid,
                                text="",
                                question_type=qtype,
                                marks=section.marks_per_question,
                                bloom_level=level,
                                topic_ids=[pool[0].id],
                                unit=unit,
                                difficulty_score=difficulty,
                            )
                        )
                        meta[vid] = (si, level, unit)

    pool_all = candidates + virtual
    model = _build_model(pattern, pool_all)
    _add_structure(model, exact_sections=True)
    for family in DISTRIBUTION_FAMILIES:
        _add_family(model, family)
    status, chosen = _solve(model, extra_costs={v.id: _VIRTUAL_COST for v in virtual}, time_limit=20.0)
    if status == "infeasible":
        # Even unlimited generation can't satisfy the distributions (e.g. a
        # Bloom's target no section allows). Fall back to filling section counts.
        model = _build_model(pattern, pool_all)
        _add_structure(model, exact_sections=True)
        _, chosen = _solve(model, extra_costs={v.id: _VIRTUAL_COST for v in virtual}, time_limit=20.0)

    requests: list[GapRequest] = []
    unit_cursor: Counter = Counter()
    type_cursor: Counter[int] = Counter()
    for qi, si in chosen:
        q = pool_all[qi]
        if not q.id.startswith(_VIRTUAL_PREFIX):
            continue
        section = pattern.sections[si]
        _, level, unit = meta[q.id]
        pool = unit_pools[unit]
        topic = pool[unit_cursor[unit] % len(pool)]
        unit_cursor[unit] += 1
        types = section.question_types or [QuestionType.SHORT_ANSWER]
        qtype = types[type_cursor[si] % len(types)]
        type_cursor[si] += 1
        requests.append(
            GapRequest(
                section=section.name,
                topic_id=topic.id,
                topic_name=topic.name,
                question_type=qtype,
                bloom_level=level,
                marks=section.marks_per_question,
                unit=unit,
            )
        )
    requests.sort(key=lambda r: [s.name for s in pattern.sections].index(r.section))
    return requests[:max_questions]
