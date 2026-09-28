from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_teacher, require_subject
from app.core.attempt_store import get_attempt_store
from app.core.config import get_settings
from app.core.exam_store import get_exam_store
from app.core.graph_store import course_outcome_node_ids, get_graph_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.exam import AssessmentType, Exam
from app.schemas.submission import Submission
from app.schemas.teacher import Teacher
from app.services.exam_attempts import AttemptState, attempt_status, finalize_ended_attempts
from app.services.performance_analytics import (
    GRADE_SCALE,
    AssessmentAnalytics,
    ClassOverview,
    TopicRisk,
    assessment_analytics,
    topic_risk,
    GradeCount,
    StudentDetail,
    class_overview,
    student_detail,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"], dependencies=[Depends(get_current_teacher)])


def _course_outcomes(subject_id: str) -> frozenset[str]:
    return frozenset(course_outcome_node_ids(get_graph_store(subject_id).graph))


def _subject_data(
    subject_id: str, teacher: Teacher, exam_type: AssessmentType | None
) -> tuple[list[Exam], list[Submission], dict, dict[str, str]]:
    """Exams + submissions for one subject the teacher owns. Students are only
    ever discovered through submissions to these exams, which is what keeps a
    teacher from seeing students of subjects they don't handle."""
    require_subject(subject_id, teacher)
    exams = [
        e
        for e in get_exam_store().list_by_subject(subject_id)
        if e.teacher_id == teacher.id and (exam_type is None or e.exam_type == exam_type)
    ]
    for e in exams:
        finalize_ended_attempts(e)  # saved work from attempts that ran out of time counts
    store = get_submission_store()
    submissions = [s for e in exams for s in store.list_by_exam(e.id)]
    bank = get_question_bank(subject_id).questions
    graph = get_graph_store(subject_id).graph
    topic_names = {nid: data.get("name", nid) for nid, data in graph.nodes(data=True)}
    return exams, submissions, bank, topic_names


@router.get("/grading-scale", response_model=list[GradeCount])
def grading_scale() -> list[GradeCount]:
    return [GradeCount(grade=g, label=label, min_percent=t, count=0) for t, g, label in GRADE_SCALE]


@router.get("/overview", response_model=ClassOverview)
def overview(
    subject_id: str, exam_type: AssessmentType | None = None, teacher: Teacher = Depends(get_current_teacher)
) -> ClassOverview:
    exams, submissions, bank, topic_names = _subject_data(subject_id, teacher, exam_type)
    return class_overview(exams, submissions, bank, topic_names, _course_outcomes(subject_id))


@router.get("/students/{student_key}", response_model=StudentDetail)
def student(
    student_key: str,
    subject_id: str,
    exam_type: AssessmentType | None = None,
    teacher: Teacher = Depends(get_current_teacher),
) -> StudentDetail:
    exams, submissions, bank, topic_names = _subject_data(subject_id, teacher, exam_type)
    detail = student_detail(student_key, exams, submissions, bank, topic_names, _course_outcomes(subject_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Student not found in this subject")
    return detail


@router.get("/exams/{exam_id}", response_model=AssessmentAnalytics)
def exam_analytics(exam_id: str, teacher: Teacher = Depends(get_current_teacher)) -> AssessmentAnalytics:
    """Assessment-level analytics for one quiz/exam, including per-question
    results and predicted-vs-actual difficulty (only where there's enough data)."""
    exam = get_exam_store().get(exam_id)
    if exam is None or exam.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Exam not found")
    require_subject(exam.subject_id, teacher)
    finalize_ended_attempts(exam)
    settings = get_settings()
    graph = get_graph_store(exam.subject_id).graph
    attempts = [AttemptState(exam_id=a.exam_id, status=attempt_status(a, exam)) for a in get_attempt_store().list_by_exam(exam.id)]
    return assessment_analytics(
        exam,
        get_submission_store().list_by_exam(exam.id),
        get_question_bank(exam.subject_id).questions,
        {nid: data.get("name", nid) for nid, data in graph.nodes(data=True)},
        attempts,
        settings.question_min_responses,
        settings.calibration_min_questions,
        _course_outcomes(exam.subject_id),
    )


@router.get("/topic-risk", response_model=TopicRisk)
def topic_risk_report(
    subject_id: str, exam_type: AssessmentType | None = None, teacher: Teacher = Depends(get_current_teacher)
) -> TopicRisk:
    """Per knowledge-graph topic: coverage risk (too few bank questions) and,
    separately, performance risk (students score poorly, with enough answers to say so)."""
    exams, submissions, bank, topic_names = _subject_data(subject_id, teacher, exam_type)
    overview = class_overview(exams, submissions, bank, topic_names, _course_outcomes(subject_id))
    counts: dict[str, int] = {}
    for q in bank.values():
        for t in q.topic_ids:
            counts[t] = counts.get(t, 0) + 1
    settings = get_settings()
    cos = course_outcome_node_ids(get_graph_store(subject_id).graph)
    topics = {tid: name for tid, name in topic_names.items() if tid not in cos}
    perf = [r for r in overview.breakdowns.topics if r.key not in cos]
    return topic_risk(topics, counts, perf, settings.topic_min_questions, settings.topic_risk_percent)
