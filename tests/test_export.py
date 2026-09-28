"""PDF export: question paper, answer key and blueprint. Output is parsed back
with pypdf (already a dependency) to check it's a valid PDF with the right content."""

import io
from datetime import timedelta

from pypdf import PdfReader

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from app.services.pdf_writer import PdfDocument, sanitize, wrap
from tests.conftest import T0
from tests.factories import make_exam, q, seed, small_pattern

MCQ, SA, CODE = QuestionType.MCQ, QuestionType.SHORT_ANSWER, QuestionType.CODE_FIX


def _text(data: bytes) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(data))
    return len(reader.pages), "\n".join(page.extract_text() for page in reader.pages)


def _export(api_client, exam_id, kind, tz=0):
    r = api_client.get(f"/api/v1/exams/{exam_id}/export/{kind}?tz_offset={tz}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-1.4") and r.content.rstrip().endswith(b"%%EOF")
    return r


def _pattern_exam(api_client):
    seed(api_client, [
        q("a1", MCQ, 1, BloomLevel.REMEMBER, text="Which structure is LIFO?"),
        *(q(f"a{i}", MCQ, 1, BloomLevel.REMEMBER) for i in range(2, 5)),
        q("b1", SA, 5, BloomLevel.APPLY, text="Explain recursion - with an example.", correct_answer="A function calling itself."),
        q("b2", CODE, 5, BloomLevel.APPLY, text="Fix the doubling program."),
    ])
    pid = small_pattern(api_client)
    return make_exam(api_client, ["a1", "a2", "a3", "a4", "b1", "b2"], name="MSE 1", pattern_id=pid, exam_type="MSE",
                     go_live=T0 + timedelta(days=2), duration=90)


def test_question_paper_pdf(api_client, clock):
    exam_id = _pattern_exam(api_client)
    r = _export(api_client, exam_id, "paper", tz=-330)  # IST
    assert 'filename="MSE_1_paper.pdf"' in r.headers["content-disposition"]
    pages, text = _text(r.content)
    assert pages >= 1
    for expected in ("Test Subject", "Mid-Semester Examination (MSE)", "MSE 1", "Teacher: Test Teacher",
                     "Duration: 90 minutes", "Maximum marks: 14", "Part A", "Part B",
                     "Which structure is LIFO?", "(a)", "right", "[5]", "Explain recursion - with an example.",
                     "print(int(input()) + 1)"):
        assert expected in text, expected
    assert "3 Oct 2026" in text  # 1 Oct 09:00 UTC + 2 days, shown in the teacher's timezone
    assert "A function calling itself" not in text  # no answers on the question paper
    assert "print(int(input()) * 2)" not in text


def test_answer_key_pdf(api_client, clock):
    exam_id = _pattern_exam(api_client)
    _, text = _text(_export(api_client, exam_id, "answer-key").content)
    assert "Answer key" in text
    assert "Answer: (a) right" in text
    assert "A function calling itself." in text
    assert "Reference solution" in text and "print(int(input()) * 2)" in text
    assert "Expected output" in text


def test_blueprint_pdf(api_client, clock):
    exam_id = _pattern_exam(api_client)
    _, text = _text(_export(api_client, exam_id, "blueprint").content)
    assert "Assessment blueprint" in text and "SATISFIES the pattern" in text
    for section in ("Sections", "Bloom's taxonomy", "Question types", "Conceptual / reasoning / coding"):
        assert section in text, section


def test_free_form_quiz_exports_without_sections(api_client, clock):
    seed(api_client, [q("x1", MCQ, 2), q("x2", SA, 3)])
    exam_id = make_exam(api_client, ["x1", "x2"], name="Weekly quiz")
    _, text = _text(_export(api_client, exam_id, "paper").content)
    assert "Quiz" in text and "Part A" not in text and "1." in text and "2." in text
    _, bp = _text(_export(api_client, exam_id, "blueprint").content)
    assert "Free-form quiz" in bp


def test_empty_exam_cannot_be_exported(api_client, clock):
    exam_id = make_exam(api_client, [], name="Empty")
    assert api_client.get(f"/api/v1/exams/{exam_id}/export/paper").status_code == 422


def test_pdf_writer_paginates_wraps_and_sanitises():
    doc = PdfDocument(title="Long", footer="Footer")
    for i in range(80):
        doc.paragraph(f"Line {i}: " + "word " * 40, right_label="[1]")
    doc.code("for i in range(10):\n    print(i)  # " + "x" * 200)
    doc.table(["A", "B"], [["1", "2"]] * 5, [0.5, 0.5])
    pages, text = _text(doc.to_bytes())
    assert pages > 3
    assert "Line 79" in text and "Page 1 of" in text
    assert sanitize("a — b ≤ c → d 中") == "a - b <= c -> d ?"
    assert all(len(line) > 0 for line in wrap("x" * 500, "regular", 10, 100))
