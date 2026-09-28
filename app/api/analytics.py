from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_teacher, require_subject
from app.core.exam_store import get_exam_store
from app.core.graph_store import get_graph_store
from app.core.question_bank import get_question_bank
from app.core.submission_store import get_submission_store
from app.schemas.exam import AssessmentType, Exam
from app.schemas.submission import Submission
from app.schemas.teacher import Teacher
from app.services.performance_analytics import (
    GRADE_SCALE,
    ClassOverview,
    GradeCount,
    StudentDetail,
    class_overview,
    student_detail,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"], dependencies=[Depends(get_current_teacher)])


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
    return class_overview(exams, submissions, bank, topic_names)


@router.get("/students/{student_key}", response_model=StudentDetail)
def student(
    student_key: str,
    subject_id: str,
    exam_type: AssessmentType | None = None,
    teacher: Teacher = Depends(get_current_teacher),
) -> StudentDetail:
    exams, submissions, bank, topic_names = _subject_data(subject_id, teacher, exam_type)
    detail = student_detail(student_key, exams, submissions, bank, topic_names)
    if detail is None:
        raise HTTPException(status_code=404, detail="Student not found in this subject")
    return detail
