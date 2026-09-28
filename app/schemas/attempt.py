from datetime import datetime, timedelta

from pydantic import BaseModel

from app.schemas.exam import Exam


class Attempt(BaseModel):
    """A student's server-side exam attempt. `started_at` is always the
    server's clock at the moment the attempt was created - clients can never
    set it - and one attempt exists per student per exam, so reconnecting or
    restarting resumes the same timer instead of resetting it."""

    id: str  # also the student's opaque attempt token
    exam_id: str
    student_key: str
    student_name: str
    student_identifier: str | None = None
    started_at: datetime
    # Frozen at start so a later edit to the exam's duration can't retroactively
    # shorten (or extend) an attempt already in progress.
    duration_minutes: int | None = None
    submitted_at: datetime | None = None
    submission_id: str | None = None
    auto_submitted: bool = False  # submitted by the server from saved answers when time ran out / exam closed

    # Server-side autosave: the student's latest answers (question id -> answer),
    # so work survives refreshes and dropped connections. Saving never touches
    # started_at or the deadline.
    saved_answers: dict[str, str] = {}
    save_seq: int = 0  # highest client sequence number applied; older/replayed saves are ignored
    last_saved_at: datetime | None = None

    def deadline(self, exam: Exam) -> datetime | None:
        """When this attempt's time runs out: start + duration, capped at the
        exam's (current) closing time. None = no time limit at all."""
        candidates = []
        if self.duration_minutes:
            candidates.append(self.started_at + timedelta(minutes=self.duration_minutes))
        if exam.closes_at is not None:
            candidates.append(exam.closes_at)
        return min(candidates) if candidates else None
