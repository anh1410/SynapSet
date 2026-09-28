"""Assessment blueprint: the paper's actual distributions next to its
pattern's targets, with pass/fail per constraint.

This is a view over the existing compliance report (pattern_assembly), not a
second implementation: for a pattern-based exam the targets, tolerance and
pass/fail come straight from `evaluate_selection`. A free-form quiz has no
targets, so the same distributions are reported for information only.
"""

from collections import defaultdict

from pydantic import BaseModel

from app.schemas.exam import Exam
from app.schemas.exam_pattern import ExamPattern
from app.schemas.question import Question
from app.schemas.skill import difficulty_bucket
from app.services.pattern_assembly import (
    _BLOOM_LABELS,
    _DIFFICULTY_LABELS,
    _SKILL_LABELS,
    _TYPE_LABELS,
    CoRow,
    DistributionRow,
    SectionReport,
    evaluate_selection,
    info_distribution,
)


class Blueprint(BaseModel):
    exam_id: str
    exam_name: str
    exam_type: str
    pattern_id: str | None
    pattern_name: str | None
    tolerance_percent: float | None
    question_count: int
    total_marks: int
    target_marks: int | None
    compliant: bool | None  # None for exams without a pattern (nothing to comply with)
    sections: list[SectionReport]
    units: list[DistributionRow]
    topics: list[DistributionRow]
    bloom: list[DistributionRow]
    difficulty: list[DistributionRow]
    question_types: list[DistributionRow]
    skills: list[DistributionRow]
    course_outcomes: list[CoRow]
    unassigned_question_ids: list[str]
    issues: list[str]


def _topic_rows(
    questions: list[Question], total: int, topic_names: dict[str, str], exclude: set[str]
) -> list[DistributionRow]:
    """Marks per knowledge-graph topic; a question tagged with several topics
    splits its marks evenly between them. Course-outcome nodes (`exclude`)
    aren't topics - COs have their own table."""
    marks: dict[str, float] = defaultdict(float)
    for q in questions:
        tags = [t for t in q.topic_ids if t not in exclude] or ["__untagged__"]
        for t in tags:
            marks[t] += q.marks / len(tags)
    rows = [
        DistributionRow(
            key=t,
            label="Untagged" if t == "__untagged__" else topic_names.get(t, t.replace("_", " ").title()),
            target_percent=None,
            actual_percent=round(100 * m / total, 1) if total else 0.0,
            actual_marks=round(m, 1),
            within_tolerance=True,
        )
        for t, m in marks.items()
    ]
    return sorted(rows, key=lambda r: -r.actual_percent)


def _untargeted_cos(questions: list[Question], total: int, targeted: set[str]) -> list[CoRow]:
    """Course outcomes the paper assesses but the pattern doesn't require."""
    marks: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for q in questions:
        for co in q.co_ids:
            if co not in targeted:
                marks[co] += q.marks
                counts[co] += 1
    return [
        CoRow(
            co_code=co,
            min_questions=0,
            min_percent=None,
            actual=counts[co],
            actual_marks=marks[co],
            actual_percent=round(100 * marks[co] / total, 1) if total else 0.0,
            met=True,
        )
        for co in sorted(marks)
    ]


def describe_paper(
    exam: Exam,
    questions: list[Question],
    pattern: ExamPattern | None,
    topic_names: dict[str, str],
    course_outcome_ids: set[str] | None = None,
) -> Blueprint:
    cos = course_outcome_ids or set()
    actual_marks = sum(q.marks for q in questions)
    common = dict(
        exam_id=exam.id,
        exam_name=exam.name,
        exam_type=exam.exam_type,
        question_count=len(questions),
        total_marks=actual_marks,
    )

    if pattern is not None:
        report = evaluate_selection(pattern, questions)
        total = pattern.total_marks
        targeted = {c.co_code for c in pattern.co_requirements}
        return Blueprint(
            **common,
            pattern_id=pattern.id,
            pattern_name=pattern.name,
            tolerance_percent=pattern.tolerance_percent,
            target_marks=total,
            compliant=report.compliant,
            sections=report.sections,
            units=report.units,
            topics=_topic_rows(questions, total, topic_names, cos),
            bloom=report.bloom,
            difficulty=report.difficulty,
            question_types=report.question_types,
            skills=report.skills,
            course_outcomes=report.course_outcomes + _untargeted_cos(questions, total, targeted),
            unassigned_question_ids=report.unassigned_question_ids,
            issues=report.issues,
        )

    total = actual_marks
    return Blueprint(
        **common,
        pattern_id=None,
        pattern_name=None,
        tolerance_percent=None,
        target_marks=None,
        compliant=None,
        sections=[],
        units=[],
        topics=_topic_rows(questions, total, topic_names, cos),
        bloom=info_distribution(questions, total, lambda q: str(int(q.bloom_level)), {str(k): v for k, v in _BLOOM_LABELS.items()}),
        difficulty=info_distribution(questions, total, lambda q: difficulty_bucket(q.difficulty_score), _DIFFICULTY_LABELS),
        question_types=info_distribution(questions, total, lambda q: q.question_type.value, _TYPE_LABELS),
        skills=info_distribution(questions, total, lambda q: q.effective_skill_category.value, _SKILL_LABELS),
        course_outcomes=_untargeted_cos(questions, total, set()),
        unassigned_question_ids=[],
        issues=[],
    )
