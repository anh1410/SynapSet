import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_teacher, require_subject
from app.core.student_store import get_student_store
from app.core.subject_store import get_subject_store
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher

router = APIRouter(prefix="/api/v1/subjects", tags=["subjects"], dependencies=[Depends(get_current_teacher)])


class CreateSubjectRequest(BaseModel):
    name: str


@router.post("", response_model=Subject)
def create_subject(request: CreateSubjectRequest, teacher: Teacher = Depends(get_current_teacher)) -> Subject:
    subject = Subject(id=str(uuid.uuid4()), teacher_id=teacher.id, name=request.name)
    return get_subject_store().assign_join_code(subject)


@router.get("", response_model=list[Subject])
def list_subjects(teacher: Teacher = Depends(get_current_teacher)) -> list[Subject]:
    return get_subject_store().list_by_teacher(teacher.id)


class JoinCodeResponse(BaseModel):
    subject_id: str
    join_code: str
    enrolled_count: int


class EnrolledStudent(BaseModel):
    id: str
    name: str
    roll_number: str
    email: str


def _join_code_response(subject: Subject) -> JoinCodeResponse:
    return JoinCodeResponse(
        subject_id=subject.id,
        join_code=subject.join_code or "",
        enrolled_count=len(get_student_store().list_by_subject(subject.id)),
    )


@router.get("/{subject_id}/join-code", response_model=JoinCodeResponse)
def get_join_code(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> JoinCodeResponse:
    """The code students use to join this subject from their dashboard
    (subjects created before join codes existed get one now)."""
    subject = require_subject(subject_id, teacher)
    if not subject.join_code:
        subject = get_subject_store().assign_join_code(subject)
    return _join_code_response(subject)


@router.post("/{subject_id}/join-code/rotate", response_model=JoinCodeResponse)
def rotate_join_code(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> JoinCodeResponse:
    """Replace the join code (e.g. it was shared too widely). Students who
    already joined stay enrolled; the old code stops working."""
    subject = require_subject(subject_id, teacher)
    return _join_code_response(get_subject_store().assign_join_code(subject))


@router.get("/{subject_id}/students", response_model=list[EnrolledStudent])
def list_enrolled_students(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[EnrolledStudent]:
    require_subject(subject_id, teacher)
    return [
        EnrolledStudent(id=s.id, name=s.name, roll_number=s.roll_number, email=s.email)
        for s in get_student_store().list_by_subject(subject_id)
    ]


@router.delete("/{subject_id}")
def delete_subject(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> dict:
    store = get_subject_store()
    subject = store.get(subject_id)
    if subject is None or subject.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Subject not found")
    store.remove(subject_id)
    return {"deleted": subject_id}
