"""How each bank question has been used: in which exams, how recently, and
how students did on it. Derived entirely from the exam and submission stores
(no separate usage records to keep in sync).

A question counts as *used* once it appears in a published exam (anything
past draft); drafts are listed but don't count, since no student has seen them.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.core import clock
from app.schemas.exam import Exam
from app.schemas.submission import Submission


class ExamUse(BaseModel):
    exam_id: str
    name: str
    exam_type: str
    bucket: str
    date: datetime  # go-live time, or creation time for unscheduled exams


class QuestionUsage(BaseModel):
    question_id: str
    times_used: int  # published exams containing the question
    exams: list[ExamUse]  # every exam containing it, drafts included, newest first
    last_used_at: datetime | None
    never_used: bool
    recently_used: bool
    frequently_used: bool
    responses: int  # graded student answers across all exams
    average_percent: float | None  # None until anyone has been graded on it


def exam_date(exam: Exam) -> datetime:
    return exam.go_live_at or exam.created_at


def usage_by_question(
    question_ids: list[str],
    exams: list[Exam],
    submissions: list[Submission],
    recent_days: int,
    frequent_count: int,
) -> dict[str, QuestionUsage]:
    uses: dict[str, list[ExamUse]] = defaultdict(list)
    for exam in exams:
        for qid in exam.question_ids:
            uses[qid].append(
                ExamUse(exam_id=exam.id, name=exam.name, exam_type=exam.exam_type, bucket=exam.bucket, date=exam_date(exam))
            )

    awarded: dict[str, float] = defaultdict(float)
    maximum: dict[str, float] = defaultdict(float)
    responses: dict[str, int] = defaultdict(int)
    for sub in submissions:
        for answer in sub.answers:
            if answer.is_graded:
                awarded[answer.question_id] += answer.marks_awarded
                maximum[answer.question_id] += answer.max_marks
                responses[answer.question_id] += 1

    cutoff = clock.utcnow() - timedelta(days=recent_days)
    result = {}
    for qid in question_ids:
        exam_uses = sorted(uses.get(qid, []), key=lambda u: u.date, reverse=True)
        published = [u for u in exam_uses if u.bucket != "draft"]
        last = published[0].date if published else None
        result[qid] = QuestionUsage(
            question_id=qid,
            times_used=len(published),
            exams=exam_uses,
            last_used_at=last,
            never_used=not published,
            recently_used=last is not None and last >= cutoff,
            frequently_used=len(published) >= frequent_count,
            responses=responses.get(qid, 0),
            average_percent=round(100 * awarded[qid] / maximum[qid], 1) if maximum.get(qid) else None,
        )
    return result


def recently_used_ids(exams: list[Exam], days: int, exclude_exam_id: str | None = None) -> set[str]:
    """Questions in a published exam dated within the last `days` days."""
    cutoff = clock.utcnow() - timedelta(days=days)
    return {
        qid
        for exam in exams
        if exam.id != exclude_exam_id and exam.bucket != "draft" and exam_date(exam) >= cutoff
        for qid in exam.question_ids
    }
