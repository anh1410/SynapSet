from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.schemas.submission import student_key


class Student(BaseModel):
    """A student account for the dashboard. The roll number is the student's
    identity on exams (see `student_key`), so it is unique across accounts;
    `subject_ids` are the subjects the student has joined with a join code."""

    id: str
    email: str
    name: str
    roll_number: str
    password_hash: str
    subject_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def key(self) -> str:
        """Same key attempts and submissions use for this student."""
        return student_key(self.name, self.roll_number)


class StudentPublic(BaseModel):
    id: str
    email: str
    name: str
    roll_number: str
    created_at: datetime

    @classmethod
    def from_student(cls, student: Student) -> "StudentPublic":
        return cls(
            id=student.id, email=student.email, name=student.name,
            roll_number=student.roll_number, created_at=student.created_at,
        )
