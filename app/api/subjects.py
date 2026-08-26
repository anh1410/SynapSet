import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_teacher
from app.core.subject_store import get_subject_store
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher

router = APIRouter(prefix="/api/v1/subjects", tags=["subjects"], dependencies=[Depends(get_current_teacher)])


class CreateSubjectRequest(BaseModel):
    name: str


@router.post("", response_model=Subject)
def create_subject(request: CreateSubjectRequest, teacher: Teacher = Depends(get_current_teacher)) -> Subject:
    subject = Subject(id=str(uuid.uuid4()), teacher_id=teacher.id, name=request.name)
    get_subject_store().add(subject)
    return subject


@router.get("", response_model=list[Subject])
def list_subjects(teacher: Teacher = Depends(get_current_teacher)) -> list[Subject]:
    return get_subject_store().list_by_teacher(teacher.id)


@router.delete("/{subject_id}")
def delete_subject(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> dict:
    store = get_subject_store()
    subject = store.get(subject_id)
    if subject is None or subject.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Subject not found")
    store.remove(subject_id)
    return {"deleted": subject_id}
