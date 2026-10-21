import math

from app.schemas.grading import GradeResult, TestCaseResult
from app.schemas.question import CODING_TYPES, Question, QuestionType
from app.services.code_sandbox import CodeTimeoutError, UnsafeCodeError, normalize_output, outputs_match, run_code

# short_answer/long_answer have no single correct string to compare against -
# those need a human to grade them, so they're deliberately excluded here.
AUTO_GRADABLE_TYPES = {QuestionType.MCQ, QuestionType.FILL_IN_BLANK, QuestionType.NUMERICAL, *CODING_TYPES}


def _grade_code(question: Question, submitted_code: str) -> GradeResult:
    """code_fix and code_write: run the submitted program against the hidden
    test cases; marks in proportion to the tests passed."""
    cases = question.test_cases or []
    if not cases:
        return GradeResult(
            correct=False, marks_awarded=0, max_marks=question.marks, detail="No test cases configured for this question"
        )

    results: list[TestCaseResult] = []
    for case in cases:
        try:
            actual = run_code(submitted_code, case.input)
            results.append(
                TestCaseResult(
                    input=case.input,
                    expected_output=case.expected_output,
                    actual_output=normalize_output(actual),
                    passed=outputs_match(actual, case.expected_output),
                )
            )
        except (UnsafeCodeError, CodeTimeoutError) as exc:
            results.append(
                TestCaseResult(
                    input=case.input, expected_output=case.expected_output, actual_output="", passed=False, error=str(exc)
                )
            )

    passed_count = sum(1 for r in results if r.passed)
    all_passed = passed_count == len(results)
    return GradeResult(
        correct=all_passed,
        marks_awarded=partial_marks(question.marks, passed_count, len(results)),
        max_marks=question.marks,
        detail=f"{passed_count}/{len(results)} test cases passed",
        test_results=results,
    )


def partial_marks(marks: int, passed: int, total: int) -> int:
    """Marks in proportion to tests passed, rounded half up (Python's round()
    is banker's rounding: 2.5 -> 2 but 1.5 -> 2). Full marks only when every
    test passes, so a 1-mark question with 2 of 3 tests passing scores 0,
    not 1."""
    if total == 0:
        return 0
    if passed == total:
        return marks
    return min(marks - 1, math.floor(marks * passed / total + 0.5)) if marks > 0 else 0


def _as_number(text: str) -> float | None:
    try:
        value = float(text.strip().replace(",", ""))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def answers_match(question: Question, answer: str) -> bool:
    """mcq / fill_in_blank: case-insensitive exact match. numerical: also
    equal as numbers, so "4.0", "4" and "4.00" all match an answer of 4."""
    if question.correct_answer is None:
        return False
    if answer.strip().lower() == question.correct_answer.strip().lower():
        return True
    if question.question_type == QuestionType.NUMERICAL:
        given, expected = _as_number(answer), _as_number(question.correct_answer)
        return given is not None and expected is not None and math.isclose(given, expected, rel_tol=1e-9, abs_tol=1e-9)
    return False


def _grade_exact_match(question: Question, answer: str) -> GradeResult:
    correct = answers_match(question, answer)
    return GradeResult(
        correct=correct,
        marks_awarded=question.marks if correct else 0,
        max_marks=question.marks,
        detail="Correct" if correct else "Incorrect",
    )


def grade_answer(question: Question, answer: str) -> GradeResult:
    """Auto-grades a submitted answer. Raises ValueError if this question
    type isn't auto-gradable (short_answer/long_answer need a human)."""
    if question.question_type in CODING_TYPES:
        return _grade_code(question, answer)
    if question.question_type in (QuestionType.MCQ, QuestionType.FILL_IN_BLANK, QuestionType.NUMERICAL):
        return _grade_exact_match(question, answer)
    raise ValueError(f"{question.question_type.value} questions require manual grading")
