from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import InvalidTokenError, decode_access_token
from app.core.student_store import get_student_store
from app.core.subject_store import get_subject_store
from app.core.teacher_store import get_teacher_store
from app.schemas.student import Student
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher

_bearer_scheme = HTTPBearer()
_optional_bearer_scheme = HTTPBearer(auto_error=False)


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


def _student_from_token(token: str) -> Student:
    try:
        student_id = decode_access_token(token, role="student")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired student session") from exc
    student = get_student_store().get(student_id)
    if student is None:
        raise HTTPException(status_code=401, detail="Invalid or expired student session")
    return student


def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Student:
    return _student_from_token(credentials.credentials)


def get_optional_student(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer_scheme),
) -> Student | None:
    """For the public exam endpoints: anonymous is fine (exam link + password).
    A valid teacher token is ignored (anonymous, as before student accounts
    existed); any other token must be a valid student token, so an expired
    student session fails loudly instead of silently starting an unlinked attempt."""
    if credentials is None:
        return None
    try:
        decode_access_token(credentials.credentials, role="teacher")
        return None
    except InvalidTokenError:
        return _student_from_token(credentials.credentials)


def require_subject(subject_id: str, teacher: Teacher) -> Subject:
    """Look up a subject and confirm it belongs to the given teacher.
    404 (not 403) so a teacher can't tell another teacher's subject id exists."""
    subject = get_subject_store().get(subject_id)
    if subject is None or subject.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject
