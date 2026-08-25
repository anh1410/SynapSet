import pytest

from app.schemas.bloom import BloomLevel
from app.schemas.question import CodeTestCase, Question, QuestionType
from app.services.grading import grade_answer


def make_code_fix_question(**overrides) -> Question:
    defaults = dict(
        id="q1",
        text="Fix the doubling function",
        question_type=QuestionType.CODE_FIX,
        marks=6,
        bloom_level=BloomLevel.APPLY,
        code_language="python",
        starter_code="n = int(input())\nprint(n + n + 1)",
        correct_answer="n = int(input())\nprint(n * 2)",
        test_cases=[
            CodeTestCase(input="3\n", expected_output="6"),
            CodeTestCase(input="10\n", expected_output="20"),
            CodeTestCase(input="0\n", expected_output="0"),
        ],
    )
    defaults.update(overrides)
    return Question(**defaults)


def test_grade_code_fix_all_tests_pass_awards_full_marks():
    question = make_code_fix_question()
    result = grade_answer(question, "n = int(input())\nprint(n * 2)")
    assert result.correct is True
    assert result.marks_awarded == 6
    assert result.detail == "3/3 test cases passed"
    assert all(r.passed for r in result.test_results)


def test_grade_code_fix_partial_pass_awards_partial_marks():
    question = make_code_fix_question()
    # Fixes the doubling but has an off-by-one that breaks only the n=0 case.
    result = grade_answer(question, "n = int(input())\nprint(n * 2 + (1 if n == 0 else 0))")
    assert result.correct is False
    assert result.marks_awarded == 4  # 2/3 passed -> round(6 * 2/3)
    assert result.detail == "2/3 test cases passed"


def test_grade_code_fix_unsafe_submission_counts_as_failed():
    question = make_code_fix_question()
    result = grade_answer(question, "import os\nprint(os.getcwd())")
    assert result.correct is False
    assert result.marks_awarded == 0
    assert all(r.error for r in result.test_results)


def test_grade_code_fix_with_no_test_cases_is_ungradeable():
    question = make_code_fix_question(test_cases=None)
    result = grade_answer(question, "print(1)")
    assert result.correct is False
    assert result.marks_awarded == 0


def test_grade_mcq_exact_match():
    question = Question(
        id="q2",
        text="2+2?",
        question_type=QuestionType.MCQ,
        marks=1,
        bloom_level=BloomLevel.REMEMBER,
        options=["3", "4", "5", "6"],
        correct_answer="4",
    )
    assert grade_answer(question, "4").correct is True
    assert grade_answer(question, "5").marks_awarded == 0


def test_grade_fill_in_blank_case_insensitive():
    question = Question(
        id="q3",
        text="The capital of France is _____.",
        question_type=QuestionType.FILL_IN_BLANK,
        marks=2,
        bloom_level=BloomLevel.REMEMBER,
        options=["Paris", "Lyon", "Nice", "Rome"],
        correct_answer="Paris",
    )
    assert grade_answer(question, "paris").correct is True


def test_grade_short_answer_raises():
    question = Question(
        id="q4", text="Explain X.", question_type=QuestionType.SHORT_ANSWER, marks=5, bloom_level=BloomLevel.UNDERSTAND
    )
    with pytest.raises(ValueError):
        grade_answer(question, "some free text")
