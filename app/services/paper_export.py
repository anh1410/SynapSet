"""Question paper, answer key and blueprint as PDFs (see pdf_writer).

Section layout comes from the pattern's compliance report, so the printed
paper is grouped exactly the way compliance was judged. Free-form quizzes
print as a single list.
"""

from datetime import datetime, timedelta, timezone

from app.schemas.exam import Exam
from app.schemas.exam_pattern import ExamPattern
from app.schemas.question import Question, QuestionType
from app.services.blueprint import Blueprint
from app.services.pattern_assembly import DistributionRow
from app.services.pdf_writer import PdfDocument

EXAM_TYPE_TITLES = {"QUIZ": "Quiz", "MSE": "Mid-Semester Examination (MSE)", "SEE": "Semester-End Examination (SEE)"}
_OBJECTIVE = {QuestionType.MCQ, QuestionType.FILL_IN_BLANK}


def _local(dt: datetime | None, tz_offset_minutes: int) -> str | None:
    """Format a UTC time in the teacher's local zone (offset as JS getTimezoneOffset reports it)."""
    if dt is None:
        return None
    local = dt.astimezone(timezone(-timedelta(minutes=tz_offset_minutes)))
    return local.strftime("%d %b %Y, %I:%M %p").replace(" 0", " ")


def _grouped(questions: list[Question], blueprint: Blueprint, pattern: ExamPattern | None):
    """[(section name, instructions, [questions])] in paper order."""
    if pattern is None or not blueprint.sections:
        return [(None, None, questions)]
    by_id = {q.id: q for q in questions}
    instructions = {s.name: s.instructions for s in pattern.sections}
    groups = []
    placed: set[str] = set()
    for sec in blueprint.sections:
        # Keep the teacher's ordering within each section.
        members = [q for q in questions if q.id in set(sec.question_ids)]
        placed |= {q.id for q in members}
        groups.append((sec.name, instructions.get(sec.name) or "", members))
    leftover = [by_id[qid] for qid in (q.id for q in questions) if qid not in placed]
    if leftover:
        groups.append(("Additional questions", "", leftover))
    return groups


def _header(doc: PdfDocument, exam: Exam, subject: str, teacher: str, tz: int, subtitle: str | None = None) -> None:
    doc.paragraph(subject, font="bold", size=15, align="center", gap_after=2)
    doc.paragraph(EXAM_TYPE_TITLES.get(exam.exam_type, exam.exam_type), size=11.5, align="center", gap_after=2)
    doc.paragraph(exam.name + (f" - {subtitle}" if subtitle else ""), font="bold", size=12, align="center", gap_after=6)
    facts = [f"Teacher: {teacher}"]
    when = _local(exam.go_live_at, tz)
    if when:
        facts.append(f"Date: {when}")
    if exam.duration_minutes:
        facts.append(f"Duration: {exam.duration_minutes} minutes")
    facts.append(f"Maximum marks: {exam.total_marks}")
    doc.paragraph("    |    ".join(facts), size=9.5, align="center", gap_after=0)
    doc.rule()


def render_paper(exam: Exam, questions: list[Question], blueprint: Blueprint, pattern: ExamPattern | None,
                 subject: str, teacher: str, tz_offset_minutes: int = 0) -> bytes:
    doc = PdfDocument(title=exam.name, footer=f"{subject} - {exam.name}")
    _header(doc, exam, subject, teacher, tz_offset_minutes)
    doc.paragraph("General instructions", font="bold", size=10.5, gap_after=2)
    general = ["Answer all questions unless a section says otherwise.", "Marks for each question are shown in brackets."]
    if any(q.question_type == QuestionType.CODE_FIX for q in questions):
        general.append("Programming questions: correct the given code so it produces the expected output.")
    for line in general:
        doc.paragraph(f"- {line}", size=9.5, indent=8, gap_after=1)

    number = 0
    for name, instructions, members in _grouped(questions, blueprint, pattern):
        if name:
            marks = sum(q.marks for q in members)
            doc.heading(f"{name}  ({len(members)} x {members[0].marks if members else 0} = {marks} marks)", size=11.5)
            if instructions:
                doc.paragraph(instructions, size=9.5, gap_after=4)
        else:
            doc.space(6)
        for q in members:
            number += 1
            doc.paragraph(f"{number}.  {q.text}", right_label=f"[{q.marks}]", size=10.5, gap_after=3)
            if q.question_type in _OBJECTIVE and q.options:
                for i, opt in enumerate(q.options):
                    doc.paragraph(f"({chr(97 + i)})  {opt}", size=10, indent=22, gap_after=1)
            if q.question_type == QuestionType.CODE_FIX and q.starter_code:
                doc.code(q.starter_code)
            doc.space(6)
    doc.rule()
    doc.paragraph("*** End of question paper ***", size=9, align="center")
    return doc.to_bytes()


def render_answer_key(exam: Exam, questions: list[Question], blueprint: Blueprint, pattern: ExamPattern | None,
                      subject: str, teacher: str, tz_offset_minutes: int = 0) -> bytes:
    doc = PdfDocument(title=f"{exam.name} - Answer key", footer=f"{subject} - {exam.name} - ANSWER KEY (confidential)")
    _header(doc, exam, subject, teacher, tz_offset_minutes, subtitle="Answer key")
    number = 0
    for name, _, members in _grouped(questions, blueprint, pattern):
        if name:
            doc.heading(name, size=11.5)
        for q in members:
            number += 1
            doc.paragraph(f"{number}.  {q.text}", right_label=f"[{q.marks}]", size=10, gap_after=2)
            if q.question_type in _OBJECTIVE and q.options and q.correct_answer in q.options:
                letter = chr(97 + q.options.index(q.correct_answer))
                doc.paragraph(f"Answer: ({letter}) {q.correct_answer}", font="bold", size=10, indent=22)
            elif q.question_type == QuestionType.CODE_FIX:
                doc.paragraph("Reference solution:", font="bold", size=10, indent=22, gap_after=1)
                doc.code(q.correct_answer or "(none recorded)", indent=22)
                if q.test_cases:
                    rows = [[c.input.replace("\n", " / ") or "(no input)", c.expected_output] for c in q.test_cases]
                    doc.table(["Test input", "Expected output"], rows, [0.5, 0.5], size=8.5)
            elif q.question_type == QuestionType.NUMERICAL:
                doc.paragraph(f"Answer: {q.correct_answer or '(none recorded)'}", font="bold", size=10, indent=22)
            else:
                label = "Model answer / key points:" if q.correct_answer else "No model answer recorded - grade manually."
                doc.paragraph(label, font="bold", size=10, indent=22, gap_after=1)
                if q.correct_answer:
                    doc.paragraph(q.correct_answer, size=9.5, indent=22)
            doc.space(5)
    return doc.to_bytes()


def _dist_rows(rows: list[DistributionRow], tolerance: float | None) -> list[list[str]]:
    out = []
    for r in rows:
        if r.target_percent is None:
            target, status = "-", "(info)"
        else:
            target = f"{r.target_percent:g}% +/- {tolerance:g}" if tolerance is not None else f"{r.target_percent:g}%"
            status = "OK" if r.within_tolerance else "NOT MET"
        out.append([r.label, target, f"{r.actual_percent:g}%", f"{r.actual_marks:g}", status])
    return out


def render_blueprint(exam: Exam, blueprint: Blueprint, subject: str, teacher: str, tz_offset_minutes: int = 0) -> bytes:
    doc = PdfDocument(title=f"{exam.name} - Blueprint", footer=f"{subject} - {exam.name} - Assessment blueprint")
    _header(doc, exam, subject, teacher, tz_offset_minutes, subtitle="Assessment blueprint")
    if blueprint.pattern_name:
        verdict = "SATISFIES the pattern" if blueprint.compliant else "DOES NOT satisfy the pattern"
        doc.paragraph(f"Pattern: {blueprint.pattern_name}  -  this paper {verdict}.", font="bold", size=10.5)
    else:
        doc.paragraph("Free-form quiz: no pattern targets; distributions shown for information.", size=10)
    doc.paragraph(
        f"Questions: {blueprint.question_count}    Total marks: {blueprint.total_marks}"
        + (f" (target {blueprint.target_marks})" if blueprint.target_marks is not None else ""),
        size=10,
    )
    if blueprint.issues:
        doc.paragraph("Issues:", font="bold", size=10, gap_after=1)
        for issue in blueprint.issues:
            doc.paragraph(f"- {issue}", size=9.5, indent=8, gap_after=1)

    headers = ["", "Target", "Actual", "Marks", "Status"]
    widths = [0.36, 0.2, 0.14, 0.12, 0.18]
    if blueprint.sections:
        doc.heading("Sections", size=11)
        doc.table(["Section", "Required", "Filled", "Marks each", "Status"],
                  [[s.name, str(s.required), str(s.filled), str(s.marks_per_question),
                    "OK" if s.filled == s.required else "NOT MET"] for s in blueprint.sections], widths)
    for title, rows in (
        ("Unit distribution", blueprint.units),
        ("Bloom's taxonomy", blueprint.bloom),
        ("Difficulty", blueprint.difficulty),
        ("Question types", blueprint.question_types),
        ("Conceptual / reasoning / coding", blueprint.skills),
        ("Topics", blueprint.topics),
    ):
        if rows:
            doc.heading(title, size=11)
            doc.table([title.split(" ")[0]] + headers[1:], _dist_rows(rows, blueprint.tolerance_percent), widths)
    if blueprint.course_outcomes:
        doc.heading("Course outcomes", size=11)
        rows = []
        for c in blueprint.course_outcomes:
            target = []
            if c.min_questions:
                target.append(f">= {c.min_questions} q")
            if c.min_percent:
                target.append(f">= {c.min_percent:g}%")
            rows.append([c.co_code, ", ".join(target) or "-", f"{c.actual_percent:g}%",
                         f"{c.actual_marks} ({c.actual} q)", ("OK" if c.met else "NOT MET") if target else "(info)"])
        doc.table(["CO"] + headers[1:], rows, widths)
    return doc.to_bytes()
