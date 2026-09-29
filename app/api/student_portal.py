"""Student dashboard API: student accounts, joining subjects with a join
code, the exams of joined subjects (with this student's attempt status) and
their results.

Student tokens carry role="student" and are refused by every teacher
endpoint (and teacher tokens here). Taking an exam still goes through the
public /exams/{id}/start flow in submissions.py; when the student is signed
in, that attempt is linked to the account (Attempt.student_id), and only
submissions linked that way are listed as the student's results.

Results show the final score and grade only once the teacher has finished
grading; until then the score so far plus the marks pending review. Never
per-question marks, correctness or the answer key.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_student
from app.api.submissions import exam_timing
from app.core import clock
from app.core.attempt_store import get_attempt_store
from app.core.exam_store import get_exam_store
from app.core.security import create_access_token, hash_password, verify_password
from app.core.student_store import get_student_store
from app.core.subject_store import get_subject_store
from app.core.submission_store import get_submission_store
from app.core.teacher_store import get_teacher_store
from app.schemas.exam import AssessmentType, Exam
from app.schemas.student import Student, StudentPublic
from app.schemas.subject import Subject
from app.schemas.submission import student_key
from app.services.exam_attempts import attempt_expired, attempt_status, finalize_ended_attempts
from app.services.performance_analytics import grade_for

router = APIRouter(prefix="/api/v1/student", tags=["student"])

MIN_PASSWORD_LENGTH = 8


# ---------- Auth ----------


class StudentSignupRequest(BaseModel):
    name: str
    roll_number: str
    email: str
    password: str


class StudentLoginRequest(BaseModel):
    email: str
    password: str


class StudentAuthResponse(BaseModel):
    access_token: str
    student: StudentPublic


@router.post("/auth/signup", response_model=StudentAuthResponse)
def signup(request: StudentSignupRequest) -> StudentAuthResponse:
    name, roll, email = request.name.strip(), request.roll_number.strip(), request.email.strip()
    if not name or not roll or not email:
        raise HTTPException(status_code=422, detail="Name, roll number and email are required")
    if len(request.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    store = get_student_store()
    if store.get_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    # The roll number is the student's identity on exams, so it can belong to one account only.
    if store.get_by_key(student_key(name, roll)) is not None:
        raise HTTPException(status_code=409, detail="An account with this roll number already exists")
    student = Student(id=str(uuid.uuid4()), email=email, name=name, roll_number=roll,
                      password_hash=hash_password(request.password))
    store.add(student)
    return StudentAuthResponse(access_token=create_access_token(student.id, role="student"),
                               student=StudentPublic.from_student(student))


@router.post("/auth/login", response_model=StudentAuthResponse)
def login(request: StudentLoginRequest) -> StudentAuthResponse:
    student = get_student_store().get_by_email(request.email)
    if student is None or not verify_password(request.password, student.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return StudentAuthResponse(access_token=create_access_token(student.id, role="student"),
                               student=StudentPublic.from_student(student))


@router.get("/auth/me", response_model=StudentPublic)
def me(student: Student = Depends(get_current_student)) -> StudentPublic:
    return StudentPublic.from_student(student)


# ---------- Subjects (enrolment) ----------


class StudentSubject(BaseModel):
    id: str
    name: str
    teacher_name: str


class JoinSubjectRequest(BaseModel):
    code: str


def _student_subject(subject: Subject) -> StudentSubject:
    teacher = get_teacher_store().get(subject.teacher_id)
    return StudentSubject(id=subject.id, name=subject.name, teacher_name=teacher.name if teacher else "")


def _joined_subjects(student: Student) -> list[Subject]:
    """Joined subjects that still exist (a teacher may have deleted one)."""
    store = get_subject_store()
    return [s for sid in student.subject_ids if (s := store.get(sid)) is not None]


@router.get("/subjects", response_model=list[StudentSubject])
def list_subjects(student: Student = Depends(get_current_student)) -> list[StudentSubject]:
    return [_student_subject(s) for s in _joined_subjects(student)]


@router.post("/subjects/join", response_model=StudentSubject)
def join_subject(request: JoinSubjectRequest, student: Student = Depends(get_current_student)) -> StudentSubject:
    subject = get_subject_store().get_by_join_code(request.code)
    if subject is None:
        raise HTTPException(status_code=404, detail="No subject has that join code")
    if subject.id not in student.subject_ids:
        student.subject_ids.append(subject.id)
        get_student_store().add(student)
    return _student_subject(subject)


@router.delete("/subjects/{subject_id}")
def leave_subject(subject_id: str, student: Student = Depends(get_current_student)) -> dict:
    if subject_id not in student.subject_ids:
        raise HTTPException(status_code=404, detail="You haven't joined this subject")
    student.subject_ids.remove(subject_id)
    get_student_store().add(student)
    return {"left": subject_id}


# ---------- Exams ----------

MyExamStatus = Literal["not_started", "in_progress", "submitted", "auto_submitted", "not_submitted", "missed"]


class StudentExamRow(BaseModel):
    id: str
    name: str
    subject_id: str
    subject_name: str
    exam_type: AssessmentType
    total_marks: int
    question_count: int
    duration_minutes: int | None
    password_required: bool  # never the password itself
    state: Literal["upcoming", "live", "closed"]
    closed_by: Literal["teacher", "schedule"] | None
    go_live_at: datetime | None
    closes_at: datetime | None
    opens_in_seconds: int | None
    closes_in_seconds: int | None
    # This student's attempt:
    #   not_started / in_progress / submitted / auto_submitted (finalised from saved answers)
    #   not_submitted (started but time ran out / exam closed with nothing saved)
    #   missed (exam closed and never started)
    my_status: MyExamStatus
    remaining_seconds: int | None = None  # while in_progress
    submitted_at: datetime | None = None


class StudentExamsResponse(BaseModel):
    server_time: datetime
    exams: list[StudentExamRow]


def _my_status(exam: Exam, student: Student, state: str) -> tuple[MyExamStatus, int | None, datetime | None]:
    attempt = get_attempt_store().find(exam.id, student.key)
    if attempt is None:
        return ("missed" if state == "closed" else "not_started"), None, None
    if attempt.submitted_at is not None:
        return ("auto_submitted" if attempt.auto_submitted else "submitted"), None, attempt.submitted_at
    if attempt_status(attempt, exam) != "in_progress" or attempt_expired(attempt, exam, clock.utcnow()):
        return "not_submitted", None, None
    deadline = attempt.deadline(exam)
    remaining = max(0, int((deadline - clock.utcnow()).total_seconds())) if deadline else None
    return "in_progress", remaining, None


@router.get("/exams", response_model=StudentExamsResponse)
def list_exams(student: Student = Depends(get_current_student)) -> StudentExamsResponse:
    """Published exams (upcoming, live, closed - never drafts) of the subjects
    this student has joined, with their own attempt status. No questions,
    passwords or answer keys."""
    rows: list[StudentExamRow] = []
    exam_store = get_exam_store()
    for subject in _joined_subjects(student):
        for exam in exam_store.list_by_subject(subject.id):
            if exam.bucket == "draft":
                continue
            finalize_ended_attempts(exam)  # same lazy finalisation as every other attempt read
            timing = exam_timing(exam)
            status, remaining, submitted_at = _my_status(exam, student, timing.state)
            rows.append(StudentExamRow(
                id=exam.id, name=exam.name, subject_id=subject.id, subject_name=subject.name,
                exam_type=exam.exam_type, total_marks=exam.total_marks, question_count=len(exam.question_ids),
                duration_minutes=exam.duration_minutes, password_required=bool(exam.password),
                state=timing.state, closed_by=timing.closed_by, go_live_at=exam.go_live_at, closes_at=exam.closes_at,
                opens_in_seconds=timing.opens_in_seconds, closes_in_seconds=timing.closes_in_seconds,
                my_status=status, remaining_seconds=remaining, submitted_at=submitted_at,
            ))
    rows.sort(key=lambda r: r.go_live_at.timestamp() if r.go_live_at else 0.0)
    return StudentExamsResponse(server_time=clock.utcnow(), exams=rows)


# ---------- Results ----------


class StudentResult(BaseModel):
    submission_id: str
    exam_id: str
    exam_name: str
    subject_name: str
    exam_type: AssessmentType | None
    submitted_at: datetime
    auto_submitted: bool
    status: Literal["graded", "pending_review"]
    # Always: marks awarded on answers graded so far, and the marks still with the teacher.
    graded_marks: int
    graded_max_marks: int
    pending_review_marks: int
    pending_review_count: int
    total_max_marks: int
    # Only once everything is graded.
    final_marks: int | None = None
    final_percent: float | None = None
    grade: str | None = None
    grade_label: str | None = None


@router.get("/results", response_model=list[StudentResult])
def list_results(student: Student = Depends(get_current_student)) -> list[StudentResult]:
    """This student's submissions from attempts started while signed in
    (newest first). A final score and grade appear only once the teacher
    has graded every answer."""
    exams, subjects = get_exam_store(), get_subject_store()
    results: list[StudentResult] = []
    for sub in get_submission_store().list_by_student(student.id):
        exam = exams.get(sub.exam_id)
        subject = subjects.get(exam.subject_id) if exam else None
        graded = [a for a in sub.answers if a.is_graded]
        pending = [a for a in sub.answers if not a.is_graded]
        row = StudentResult(
            submission_id=sub.id, exam_id=sub.exam_id,
            exam_name=exam.name if exam else "Deleted exam", subject_name=subject.name if subject else "",
            exam_type=exam.exam_type if exam else None,
            submitted_at=sub.submitted_at, auto_submitted=sub.auto_submitted,
            status="pending_review" if pending else "graded",
            graded_marks=sum(a.marks_awarded for a in graded), graded_max_marks=sum(a.max_marks for a in graded),
            pending_review_marks=sum(a.max_marks for a in pending), pending_review_count=len(pending),
            total_max_marks=sub.total_max_marks,
        )
        if not pending and sub.total_max_marks > 0:
            percent = round(100 * sub.total_marks_awarded / sub.total_max_marks, 1)
            grade = grade_for(percent)
            row.final_marks, row.final_percent = sub.total_marks_awarded, percent
            row.grade, row.grade_label = grade if grade else (None, None)
        results.append(row)
    return results
