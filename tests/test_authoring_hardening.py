"""Hardening of the coding/authoring features: sandbox escape blocking and
fewer false rejections, tolerant output comparison, numeric answers,
half-up partial marks, scenario style kept on regenerate, teacher-written
evidence note, difficulty scored on save."""

from datetime import timedelta

import pytest

from app.schemas.bloom import BloomLevel
from app.schemas.question import CodeTestCase, Question, QuestionType
from app.services.code_sandbox import UnsafeCodeError, check_code_safety, outputs_match, run_code
from app.services.grading import grade_answer, partial_marks
from tests.conftest import T0
from tests.factories import make_exam, q, seed, seed_graph

CW = QuestionType.CODE_WRITE

# ---------- sandbox ----------

ESCAPES = [
    "print(().__class__.__base__.__subclasses__())",
    "x = type(()).__base__\nprint(x.__subclasses__())",
    "def f():\n    pass\nprint(f.__globals__)",
    "g = (i for i in [1])\nprint(g.gi_frame.f_globals)",
    "print([].__class__.__mro__)",
    "print(__builtins__)",
    "class A:\n    pass\nprint(A.__dict__)",
]


@pytest.mark.parametrize("source", ESCAPES)
def test_introspection_escapes_are_blocked(source):
    with pytest.raises(UnsafeCodeError):
        check_code_safety(source)


@pytest.mark.parametrize("source, expected", [
    ('print("The shop is open")', "The shop is open"),
    ("# open the file? no - just print\nprint('sys admin')", "sys admin"),
    ("name = 'vars'\nprint(f'{name} and open doors')", "vars and open doors"),
])
def test_banned_words_inside_strings_and_comments_are_fine(source, expected):
    assert run_code(source).strip() == expected


@pytest.mark.parametrize("source", [
    "f = open\nprint(1)",  # the name itself, not just a call
    "import sys\nprint(1)",
    "print(eval('1+1'))",
    "x = f'{open}'",  # inside an f-string expression is still code
])
def test_banned_names_in_code_are_still_rejected(source):
    with pytest.raises(UnsafeCodeError):
        check_code_safety(source)


def test_everyday_class_code_still_works():
    source = (
        "class Stack:\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "    def __len__(self):\n"
        "        return len(self.items)\n"
        "    def __str__(self):\n"
        "        return type(self).__name__ + str(self.items)\n"
        "class Counted(Stack):\n"
        "    def __init__(self):\n"
        "        super().__init__()\n"
        "        self.items.append(1)\n"
        "c = Counted()\n"
        "print(len(c), c)\n"
    )
    assert run_code(source).strip() == "1 Counted[1]"


# ---------- output comparison & grading ----------


def test_outputs_match_ignores_line_end_whitespace_and_crlf():
    assert outputs_match("1 2 3 \n4 5 \n\n", "1 2 3\n4 5")
    assert outputs_match("a\r\nb\r\n", "a\nb")
    assert not outputs_match("1 2 3", "1  2 3")  # inner spacing still matters
    assert not outputs_match("a\nb", "ab")


def _code_question(**kw):
    fields = dict(id="c", text="Print the numbers 1..n.", question_type=CW, marks=5, bloom_level=BloomLevel.APPLY,
                  code_language="python", correct_answer="n=int(input())\nprint(*range(1, n + 1))",
                  test_cases=[CodeTestCase(input="3\n", expected_output="1 2 3"),
                              CodeTestCase(input="1\n", expected_output="1")])
    fields.update(kw)
    return Question(**fields)


def test_trailing_spaces_in_student_output_do_not_cost_marks():
    student = "n = int(input())\nfor i in range(1, n + 1):\n    print(i, end=' ')\nprint()"
    result = grade_answer(_code_question(), student)
    assert result.correct and result.marks_awarded == 5


def test_student_program_printing_open_is_graded_normally():
    question = _code_question(test_cases=[CodeTestCase(input="", expected_output="Shop is open")])
    assert grade_answer(question, "print('Shop is open')").marks_awarded == 5


@pytest.mark.parametrize("given, ok", [("4", True), ("4.0", True), ("4.00", True), (" 4 ", True),
                                       ("4e0", True), ("5", False), ("four", False), ("", False)])
def test_numerical_answers_compare_as_numbers(given, ok):
    question = q("n1", QuestionType.NUMERICAL, 2, correct_answer="4")
    assert grade_answer(question, given).correct is ok


def test_mcq_is_not_compared_as_numbers():
    question = q("m1", QuestionType.MCQ, 1, options=["4", "8"], correct_answer="4")
    assert grade_answer(question, "4.0").correct is False


@pytest.mark.parametrize("marks, passed, total, expected", [
    (6, 2, 3, 4), (5, 1, 2, 3), (3, 1, 2, 2), (8, 2, 3, 5), (4, 3, 3, 4), (2, 0, 3, 0),
    (1, 2, 3, 0),  # partial never equals full marks
    (2, 2, 3, 1),
])
def test_partial_marks_round_half_up_and_never_reach_full(marks, passed, total, expected):
    assert partial_marks(marks, passed, total) == expected


# ---------- integration ----------


def test_regenerate_keeps_interview_scenario_style(api_client, clock, monkeypatch):
    seed_graph(api_client, {"queues": "Queues"})
    scenario = _code_question(id="s1", topic_ids=["queues"], scenario_based=True, difficulty_score=5.0)
    seed(api_client, [scenario])
    exam_id = make_exam(api_client, ["s1"], go_live=T0 + timedelta(days=1))
    calls = []

    def fake_generate(**kw):
        calls.append(kw)
        return [_code_question(id="new", topic_ids=["queues"], scenario_based=kw.get("scenario_based", False),
                               text="A ride-sharing dispatcher...", difficulty_score=5.0)]

    monkeypatch.setattr("app.api.paper_review.generate_questions", fake_generate)
    monkeypatch.setattr("app.api.paper_review.score_difficulty", lambda qq, gs: type("D", (), {"score": 5.0})())
    r = api_client.post(f"/api/v1/exams/{exam_id}/review/regenerate", json={"target_id": "s1", "force_new": True})
    assert r.status_code == 200, r.text
    assert calls[0]["scenario_based"] is True and calls[0]["question_type"] == CW
    assert r.json()["question"]["scenario_based"] is True


def test_evidence_note_for_teacher_written_questions(api_client, monkeypatch):
    monkeypatch.setattr("app.services.evidence.query_similar_chunks", lambda *a, **k: [])
    seed(api_client, [q("mine", origin="manual"), q("old")])
    sid = api_client.subject_id
    mine = api_client.get(f"/api/v1/questions/mine/evidence?subject_id={sid}").json()
    old = api_client.get(f"/api/v1/questions/old/evidence?subject_id={sid}").json()
    assert mine["note"].startswith("Written by the teacher") and mine["recorded"] is False
    assert not old["note"].startswith("Written by the teacher")


def test_save_scores_difficulty_only_when_missing(api_client):
    sid = api_client.subject_id
    base = {"text": "Explain how a hash table resolves collisions with chaining.", "question_type": "short_answer",
            "marks": 5, "bloom_level": 2, "origin": "manual"}
    api_client.post(f"/api/v1/questions?subject_id={sid}", json={**base, "id": "scored", "difficulty_score": None})
    api_client.post(f"/api/v1/questions?subject_id={sid}", json={**base, "id": "kept", "difficulty_score": 3.3})
    bank = {x["id"]: x for x in api_client.get(f"/api/v1/questions?subject_id={sid}").json()}
    assert 1 <= bank["scored"]["difficulty_score"] <= 10
    assert bank["kept"]["difficulty_score"] == 3.3
