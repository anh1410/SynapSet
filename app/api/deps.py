from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import InvalidTokenError, decode_access_token
from app.core.subject_store import get_subject_store
from app.core.teacher_store import get_teacher_store
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher

_bearer_scheme = HTTPBearer()


def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Teacher:
    try:
        teacher_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    teacher = get_teacher_store().get(teacher_id)
    if teacher is None:
        raise HTTPException(status_code=401, detail="Teacher not found")
    return teacher


def require_subject(subject_id: str, teacher: Teacher) -> Subject:
    """Look up a subject and confirm it belongs to the given teacher.
    404 (not 403) so a teacher can't tell another teacher's subject id exists."""
    subject = get_subject_store().get(subject_id)
    if subject is None or subject.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject
