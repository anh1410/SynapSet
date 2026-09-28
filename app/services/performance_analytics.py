"""Student performance analytics for a teacher's subject.

Everything here is computed from real graded submissions - nothing is
estimated or filled in. Answers still awaiting manual grading are counted as
"pending" and excluded from percentages (never treated as zero), and any
breakdown with too little evidence is flagged rather than labelled a strength
or weakness.

Question metadata (Bloom's level, topics, skill category, difficulty) comes
from the snapshot stored on each graded answer at submission time, falling
back to the current question bank for submissions recorded before snapshots
existed.

Students have no accounts in SynapSet - they identify themselves when they
submit - so a student is keyed by their identifier (roll number), or by name
when no identifier was given. Only submissions to exams in the requested
subject are ever read, so a teacher can't see students from other subjects.
"""

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Literal

from pydantic import BaseModel

from app.schemas.bloom import BloomLevel
from app.schemas.exam import Exam
from app.schemas.question import Question
from app.schemas.skill import SkillCategory, difficulty_bucket, resolve_skill_category
from app.schemas.submission import GradedAnswer, Submission
from app.schemas.submission import student_key as _student_key

# ---------- grading scale ----------

# 10-point (UGC/CBCS-style) letter grades on percentage of graded marks.
GRADE_SCALE: list[tuple[float, str, str]] = [
    (90, "O", "Outstanding"),
    (80, "A+", "Excellent"),
    (70, "A", "Very Good"),
    (60, "B+", "Good"),
    (50, "B", "Above Average"),
    (45, "C", "Average"),
    (40, "P", "Pass"),
    (0, "F", "Fail"),
]
PASS_PERCENT = 40.0

Band = Literal["strong", "developing", "needs_support", "insufficient"]
STRONG_PERCENT = 75.0
DEVELOPING_PERCENT = 50.0
# A topic/skill needs at least this many graded answers behind it before we
# call it a strength or weakness.
MIN_EVIDENCE = 2

SKILL_LABELS = {
    SkillCategory.CONCEPTUAL: "Conceptual understanding",
    SkillCategory.REASONING: "Reasoning & analysis",
    SkillCategory.CODING: "Coding",
}
_TESTS_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s+test cases passed")


def grade_for(percent: float | None) -> tuple[str, str] | None:
    if percent is None:
        return None
    for threshold, grade, label in GRADE_SCALE:
        if percent >= threshold:
            return grade, label
    return GRADE_SCALE[-1][1], GRADE_SCALE[-1][2]


def band_for(percent: float | None, evidence: int) -> Band:
    if percent is None or evidence < MIN_EVIDENCE:
        return "insufficient"
    if percent >= STRONG_PERCENT:
        return "strong"
    if percent >= DEVELOPING_PERCENT:
        return "developing"
    return "needs_support"


def student_key(submission: Submission) -> str:
    return _student_key(submission.student_name, submission.student_identifier)


# ---------- response models ----------


class ScoreStat(BaseModel):
    awarded: float
    max: float
    percent: float | None  # None when nothing in this group has been graded yet
    answers: int  # graded answers behind the figure
    pending: int  # answers still awaiting manual grading


class GradeInfo(BaseModel):
    grade: str
    label: str


class SkillRow(BaseModel):
    skill: SkillCategory
    label: str
    score: ScoreStat
    band: Band


class BreakdownRow(BaseModel):
    key: str
    label: str
    score: ScoreStat
    band: Band


class CodingTests(BaseModel):
    passed: int
    total: int
    percent: float | None


class Breakdowns(BaseModel):
    skills: list[SkillRow]
    coding_tests: CodingTests | None
    bloom: list[BreakdownRow]
    topics: list[BreakdownRow]
    question_types: list[BreakdownRow]
    difficulty: list[BreakdownRow]
    strengths: list[BreakdownRow]  # topics
    weaknesses: list[BreakdownRow]  # topics


class TrendPoint(BaseModel):
    exam_id: str
    name: str
    date: datetime
    percent: float | None


class AssessmentRow(BaseModel):
    exam_id: str
    name: str
    exam_type: str
    date: datetime
    total_marks: int
    submissions: int
    average_percent: float | None
    highest_percent: float | None
    lowest_percent: float | None
    pending: int


class StudentRow(BaseModel):
    key: str
    name: str
    identifier: str | None
    assessments: int
    percent: float | None
    grade: GradeInfo | None
    band: Band
    skills: dict[str, float | None]  # skill -> percent
    trend_delta: float | None  # latest assessment % minus first assessment %
    pending: int
    last_submitted_at: datetime


class HistogramBin(BaseModel):
    start: int
    end: int
    count: int


class GradeCount(BaseModel):
    grade: str
    label: str
    min_percent: float
    count: int


class ClassSummary(BaseModel):
    students: int
    assessments: int
    submissions: int
    average_percent: float | None
    median_percent: float | None
    highest_percent: float | None
    lowest_percent: float | None
    pass_rate: float | None
    pending_answers: int


class ClassOverview(BaseModel):
    summary: ClassSummary
    grade_distribution: list[GradeCount]
    score_histogram: list[HistogramBin]
    breakdowns: Breakdowns
    assessments: list[AssessmentRow]
    trend: list[TrendPoint]
    students: list[StudentRow]


class HistoryRow(BaseModel):
    exam_id: str
    name: str
    exam_type: str
    date: datetime
    submitted_at: datetime
    awarded: float
    max: float
    percent: float | None
    grade: GradeInfo | None
    class_average_percent: float | None
    pending: int


class StudentSummary(BaseModel):
    assessments: int
    percent: float | None
    grade: GradeInfo | None
    band: Band
    rank: int | None
    class_size: int
    class_average_percent: float | None
    pending_answers: int


class StudentDetail(BaseModel):
    key: str
    name: str
    identifier: str | None
    summary: StudentSummary
    history: list[HistoryRow]
    breakdowns: Breakdowns
    trend: list[TrendPoint]


# ---------- fact extraction ----------


@dataclass
class AnswerFact:
    student: str
    exam_id: str
    question_type: str
    bloom_level: int | None
    skill: SkillCategory | None
    topic_ids: list[str]
    difficulty: str | None
    awarded: float
    max: float
    graded: bool
    tests_passed: int | None
    tests_total: int | None


def _fact(student: str, exam_id: str, answer: GradedAnswer, question: Question | None) -> AnswerFact:
    bloom = answer.bloom_level if answer.bloom_level is not None else (int(question.bloom_level) if question else None)
    topics = answer.topic_ids if answer.topic_ids is not None else (question.topic_ids if question else [])
    override = answer.skill_category or (question.skill_category if question else None)
    qtype = answer.question_type.value
    if bloom is not None or override or qtype == "code_fix":
        skill = resolve_skill_category(qtype, bloom or 0, override)
    else:
        skill = None
    if answer.difficulty_score is not None:
        difficulty = difficulty_bucket(answer.difficulty_score)
    elif question is not None:
        difficulty = difficulty_bucket(question.difficulty_score)
    else:
        difficulty = None

    passed, total = answer.test_cases_passed, answer.test_cases_total
    if qtype == "code_fix" and total is None and answer.auto_graded:
        match = _TESTS_RE.search(answer.detail or "")
        if match:
            passed, total = int(match.group(1)), int(match.group(2))

    return AnswerFact(
        student=student,
        exam_id=exam_id,
        question_type=qtype,
        bloom_level=bloom,
        skill=skill,
        topic_ids=list(topics or []),
        difficulty=difficulty,
        awarded=float(answer.marks_awarded),
        max=float(answer.max_marks),
        graded=answer.is_graded,
        tests_passed=passed,
        tests_total=total,
    )


def latest_attempts(submissions: Iterable[Submission]) -> list[Submission]:
    """One submission per (student, exam): the most recent attempt."""
    latest: dict[tuple[str, str], Submission] = {}
    for sub in submissions:
        k = (student_key(sub), sub.exam_id)
        if k not in latest or sub.submitted_at > latest[k].submitted_at:
            latest[k] = sub
    return list(latest.values())


# ---------- aggregation ----------


def _score(facts: Iterable[AnswerFact]) -> ScoreStat:
    awarded = max_marks = 0.0
    answers = pending = 0
    for f in facts:
        if f.graded:
            awarded += f.awarded
            max_marks += f.max
            answers += 1
        else:
            pending += 1
    percent = round(100 * awarded / max_marks, 1) if max_marks else None
    return ScoreStat(awarded=awarded, max=max_marks, percent=percent, answers=answers, pending=pending)


def _group(facts: list[AnswerFact], keys: Callable[[AnswerFact], Iterable[str]]) -> dict[str, list[AnswerFact]]:
    groups: dict[str, list[AnswerFact]] = defaultdict(list)
    for f in facts:
        for k in keys(f):
            groups[k].append(f)
    return groups


def _rows(groups: dict[str, list[AnswerFact]], label: Callable[[str], str], order: list[str] | None = None) -> list[BreakdownRow]:
    keys = [k for k in order if k in groups] if order else sorted(groups)
    rows = []
    for k in keys:
        score = _score(groups[k])
        rows.append(BreakdownRow(key=k, label=label(k), score=score, band=band_for(score.percent, score.answers)))
    return rows


def breakdowns(facts: list[AnswerFact], topic_names: dict[str, str]) -> Breakdowns:
    skill_groups = _group(facts, lambda f: [f.skill.value] if f.skill else [])
    skills = []
    for skill in SkillCategory:
        group = skill_groups.get(skill.value, [])
        if not group:
            continue
        score = _score(group)
        skills.append(SkillRow(skill=skill, label=SKILL_LABELS[skill], score=score, band=band_for(score.percent, score.answers)))

    code_facts = [f for f in facts if f.graded and f.tests_total]
    coding_tests = None
    if code_facts:
        passed = sum(f.tests_passed or 0 for f in code_facts)
        total = sum(f.tests_total or 0 for f in code_facts)
        coding_tests = CodingTests(passed=passed, total=total, percent=round(100 * passed / total, 1) if total else None)

    bloom = _rows(
        _group(facts, lambda f: [str(f.bloom_level)] if f.bloom_level else []),
        lambda k: BloomLevel(int(k)).name.title(),
        order=[str(b.value) for b in BloomLevel],
    )
    topics = _rows(_group(facts, lambda f: f.topic_ids), lambda k: topic_names.get(k, k.replace("_", " ").title()))
    topics.sort(key=lambda r: (r.score.percent is None, -(r.score.percent or 0)))
    qtypes = _rows(_group(facts, lambda f: [f.question_type]), lambda k: k.replace("_", " ").title())
    difficulty = _rows(
        _group(facts, lambda f: [f.difficulty] if f.difficulty else []),
        lambda k: k.title(),
        order=["easy", "medium", "hard"],
    )
    strengths = [r for r in topics if r.band == "strong"][:5]
    weaknesses = sorted((r for r in topics if r.band == "needs_support"), key=lambda r: r.score.percent or 0)[:5]
    return Breakdowns(
        skills=skills,
        coding_tests=coding_tests,
        bloom=bloom,
        topics=topics,
        question_types=qtypes,
        difficulty=difficulty,
        strengths=strengths,
        weaknesses=weaknesses,
    )


def _exam_date(exam: Exam, subs: list[Submission]) -> datetime:
    if exam.go_live_at:
        return exam.go_live_at
    if subs:
        return min(s.submitted_at for s in subs)
    return exam.created_at


@dataclass
class _Dataset:
    exams: dict[str, Exam]
    subs: list[Submission]  # latest attempt per (student, exam)
    facts: list[AnswerFact]
    facts_by_sub: dict[str, list[AnswerFact]]
    exam_dates: dict[str, datetime]


def _dataset(exams: list[Exam], submissions: list[Submission], bank: dict[str, Question]) -> _Dataset:
    exam_map = {e.id: e for e in exams}
    subs = [s for s in latest_attempts(submissions) if s.exam_id in exam_map]
    facts_by_sub = {
        s.id: [_fact(student_key(s), s.exam_id, a, bank.get(a.question_id)) for a in s.answers] for s in subs
    }
    by_exam: dict[str, list[Submission]] = defaultdict(list)
    for s in subs:
        by_exam[s.exam_id].append(s)
    dates = {eid: _exam_date(e, by_exam.get(eid, [])) for eid, e in exam_map.items()}
    return _Dataset(
        exams=exam_map,
        subs=subs,
        facts=[f for fs in facts_by_sub.values() for f in fs],
        facts_by_sub=facts_by_sub,
        exam_dates=dates,
    )


def _pct(facts: list[AnswerFact]) -> float | None:
    return _score(facts).percent


def _student_rows(ds: _Dataset) -> list[StudentRow]:
    by_student: dict[str, list[Submission]] = defaultdict(list)
    for s in ds.subs:
        by_student[student_key(s)].append(s)
    rows = []
    for key, subs in by_student.items():
        subs.sort(key=lambda s: ds.exam_dates[s.exam_id])
        facts = [f for s in subs for f in ds.facts_by_sub[s.id]]
        score = _score(facts)
        skill_groups = _group(facts, lambda f: [f.skill.value] if f.skill else [])
        per_exam = [_pct(ds.facts_by_sub[s.id]) for s in subs]
        graded = [p for p in per_exam if p is not None]
        latest = max(subs, key=lambda s: s.submitted_at)
        grade = grade_for(score.percent)
        rows.append(
            StudentRow(
                key=key,
                name=latest.student_name,
                identifier=latest.student_identifier,
                assessments=len(subs),
                percent=score.percent,
                grade=GradeInfo(grade=grade[0], label=grade[1]) if grade else None,
                band=band_for(score.percent, score.answers),
                skills={skill.value: _pct(skill_groups.get(skill.value, [])) for skill in SkillCategory},
                trend_delta=round(graded[-1] - graded[0], 1) if len(graded) >= 2 else None,
                pending=score.pending,
                last_submitted_at=latest.submitted_at,
            )
        )
    rows.sort(key=lambda r: (r.percent is None, -(r.percent or 0), r.name.lower()))
    return rows


def _assessment_rows(ds: _Dataset) -> list[AssessmentRow]:
    rows = []
    for eid, exam in ds.exams.items():
        subs = [s for s in ds.subs if s.exam_id == eid]
        if not subs:
            continue
        pcts = [p for s in subs if (p := _pct(ds.facts_by_sub[s.id])) is not None]
        rows.append(
            AssessmentRow(
                exam_id=eid,
                name=exam.name,
                exam_type=exam.exam_type,
                date=ds.exam_dates[eid],
                total_marks=exam.total_marks,
                submissions=len(subs),
                average_percent=_pct([f for s in subs for f in ds.facts_by_sub[s.id]]),
                highest_percent=max(pcts) if pcts else None,
                lowest_percent=min(pcts) if pcts else None,
                pending=sum(1 for s in subs for f in ds.facts_by_sub[s.id] if not f.graded),
            )
        )
    rows.sort(key=lambda r: r.date)
    return rows


def class_overview(
    exams: list[Exam], submissions: list[Submission], bank: dict[str, Question], topic_names: dict[str, str]
) -> ClassOverview:
    ds = _dataset(exams, submissions, bank)
    students = _student_rows(ds)
    assessments = _assessment_rows(ds)
    pcts = [s.percent for s in students if s.percent is not None]

    grade_counts = {g: 0 for _, g, _ in GRADE_SCALE}
    for s in students:
        if s.grade:
            grade_counts[s.grade.grade] += 1
    bins = [HistogramBin(start=b, end=b + 10, count=0) for b in range(0, 100, 10)]
    for p in pcts:
        bins[min(int(p // 10), 9)].count += 1

    return ClassOverview(
        summary=ClassSummary(
            students=len(students),
            assessments=len(assessments),
            submissions=len(ds.subs),
            average_percent=round(statistics.mean(pcts), 1) if pcts else None,
            median_percent=round(statistics.median(pcts), 1) if pcts else None,
            highest_percent=max(pcts) if pcts else None,
            lowest_percent=min(pcts) if pcts else None,
            pass_rate=round(100 * sum(1 for p in pcts if p >= PASS_PERCENT) / len(pcts), 1) if pcts else None,
            pending_answers=sum(1 for f in ds.facts if not f.graded),
        ),
        grade_distribution=[
            GradeCount(grade=g, label=label, min_percent=t, count=grade_counts[g]) for t, g, label in GRADE_SCALE
        ],
        score_histogram=bins,
        breakdowns=breakdowns(ds.facts, topic_names),
        assessments=assessments,
        trend=[TrendPoint(exam_id=a.exam_id, name=a.name, date=a.date, percent=a.average_percent) for a in assessments],
        students=students,
    )


def student_detail(
    key: str,
    exams: list[Exam],
    submissions: list[Submission],
    bank: dict[str, Question],
    topic_names: dict[str, str],
) -> StudentDetail | None:
    ds = _dataset(exams, submissions, bank)
    mine = sorted((s for s in ds.subs if student_key(s) == key), key=lambda s: ds.exam_dates[s.exam_id])
    if not mine:
        return None

    students = _student_rows(ds)
    ranked = [r for r in students if r.percent is not None]
    me = next(r for r in students if r.key == key)
    rank = next((i + 1 for i, r in enumerate(ranked) if r.key == key), None)
    class_pcts = [r.percent for r in ranked]

    history = []
    for s in mine:
        facts = ds.facts_by_sub[s.id]
        score = _score(facts)
        grade = grade_for(score.percent)
        classmates = [f for other in ds.subs if other.exam_id == s.exam_id for f in ds.facts_by_sub[other.id]]
        exam = ds.exams[s.exam_id]
        history.append(
            HistoryRow(
                exam_id=s.exam_id,
                name=exam.name,
                exam_type=exam.exam_type,
                date=ds.exam_dates[s.exam_id],
                submitted_at=s.submitted_at,
                awarded=score.awarded,
                max=score.max,
                percent=score.percent,
                grade=GradeInfo(grade=grade[0], label=grade[1]) if grade else None,
                class_average_percent=_pct(classmates),
                pending=score.pending,
            )
        )

    facts = [f for s in mine for f in ds.facts_by_sub[s.id]]
    return StudentDetail(
        key=key,
        name=me.name,
        identifier=me.identifier,
        summary=StudentSummary(
            assessments=len(mine),
            percent=me.percent,
            grade=me.grade,
            band=me.band,
            rank=rank,
            class_size=len(ranked),
            class_average_percent=round(statistics.mean(class_pcts), 1) if class_pcts else None,
            pending_answers=me.pending,
        ),
        history=history,
        breakdowns=breakdowns(facts, topic_names),
        trend=[TrendPoint(exam_id=h.exam_id, name=h.name, date=h.date, percent=h.percent) for h in history],
    )
