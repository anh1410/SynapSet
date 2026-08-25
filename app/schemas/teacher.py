from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Teacher(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TeacherPublic(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime

    @classmethod
    def from_teacher(cls, teacher: Teacher) -> "TeacherPublic":
        return cls(id=teacher.id, email=teacher.email, name=teacher.name, created_at=teacher.created_at)
