from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.schemas.constraints import PaperConstraints
from app.schemas.question import Question


@dataclass
class OptimizationResult:
    selected: list[Question]
    status: str  # "OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"


def optimize_paper(
    candidates: list[Question],
    constraints: PaperConstraints,
    bloom_tolerance: float = 0.1,
    unit_tolerance: int = 2,
    max_time_seconds: float = 10.0,
) -> OptimizationResult:
    """Select a subset of `candidates` that exactly/near-exactly satisfies
    `constraints` via CP-SAT, maximizing the number of distinct topics covered.

    Bloom-level and unit-marks targets are enforced within a tolerance band
    (exact equality on discrete marks is usually infeasible); total marks and
    CO coverage minimums are enforced exactly.
    """
    model = cp_model.CpModel()
    n = len(candidates)
    x = [model.NewBoolVar(f"x_{i}") for i in range(n)]

    if constraints.num_questions is not None:
        model.Add(sum(x) == constraints.num_questions)

    model.Add(sum(x[i] * candidates[i].marks for i in range(n)) == constraints.total_marks)

    for bloom_level, weight in constraints.bloom_distribution.weights.items():
        relevant = [x[i] * candidates[i].marks for i in range(n) if candidates[i].bloom_level == bloom_level]
        if not relevant:
            continue
        target = weight * constraints.total_marks
        band = bloom_tolerance * constraints.total_marks
        model.Add(sum(relevant) >= max(0, int(target - band)))
        model.Add(sum(relevant) <= int(target + band) + 1)

    for co_id, min_count in constraints.co_coverage.items():
        relevant = [x[i] for i in range(n) if co_id in candidates[i].co_ids]
        if relevant:
            model.Add(sum(relevant) >= min_count)

    for unit, target_marks in constraints.unit_marks.items():
        relevant = [x[i] * candidates[i].marks for i in range(n) if candidates[i].unit == unit]
        if relevant:
            model.Add(sum(relevant) >= max(0, target_marks - unit_tolerance))
            model.Add(sum(relevant) <= target_marks + unit_tolerance)

    if constraints.allowed_question_types is not None:
        allowed = set(constraints.allowed_question_types)
        for i in range(n):
            if candidates[i].question_type not in allowed:
                model.Add(x[i] == 0)

    # Objective: maximize distinct topic coverage (a diversity proxy).
    all_topics = sorted({t for q in candidates for t in q.topic_ids})
    covered_vars = []
    for topic in all_topics:
        covers = [x[i] for i in range(n) if topic in candidates[i].topic_ids]
        if not covers:
            continue
        covered = model.NewBoolVar(f"covered_{topic}")
        model.AddMaxEquality(covered, covers)
        covered_vars.append(covered)
    if covered_vars:
        model.Maximize(sum(covered_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    status = solver.Solve(model)

    selected = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selected = [candidates[i] for i in range(n) if solver.Value(x[i])]

    return OptimizationResult(selected=selected, status=solver.StatusName(status))
