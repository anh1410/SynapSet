from app.schemas.grading import GradeResult, TestCaseResult
from app.schemas.question import Question, QuestionType
from app.services.code_sandbox import CodeTimeoutError, UnsafeCodeError, run_code

# short_answer/long_answer have no single correct string to compare against -
# those need a human to grade them, so they're deliberately excluded here.
AUTO_GRADABLE_TYPES = {QuestionType.MCQ, QuestionType.FILL_IN_BLANK, QuestionType.NUMERICAL, QuestionType.CODE_FIX}


def _grade_code_fix(question: Question, submitted_code: str) -> GradeResult:
    cases = question.test_cases or []
    if not cases:
        return GradeResult(
            correct=False, marks_awarded=0, max_marks=question.marks, detail="No test cases configured for this question"
        )

    results: list[TestCaseResult] = []
    for case in cases:
        try:
            actual = run_code(submitted_code, case.input).strip()
            results.append(
                TestCaseResult(
                    input=case.input,
                    expected_output=case.expected_output,
                    actual_output=actual,
                    passed=actual == case.expected_output.strip(),
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
    marks_awarded = question.marks if all_passed else round(question.marks * passed_count / len(results))
    return GradeResult(
        correct=all_passed,
        marks_awarded=marks_awarded,
        max_marks=question.marks,
        detail=f"{passed_count}/{len(results)} test cases passed",
        test_results=results,
    )


def _grade_exact_match(question: Question, answer: str) -> GradeResult:
    correct = question.correct_answer is not None and answer.strip().lower() == question.correct_answer.strip().lower()
    return GradeResult(
        correct=correct,
        marks_awarded=question.marks if correct else 0,
        max_marks=question.marks,
        detail="Correct" if correct else "Incorrect",
    )


def grade_answer(question: Question, answer: str) -> GradeResult:
    """Auto-grades a submitted answer. Raises ValueError if this question
    type isn't auto-gradable (short_answer/long_answer need a human)."""
    if question.question_type == QuestionType.CODE_FIX:
        return _grade_code_fix(question, answer)
    if question.question_type in (QuestionType.MCQ, QuestionType.FILL_IN_BLANK, QuestionType.NUMERICAL):
        return _grade_exact_match(question, answer)
    raise ValueError(f"{question.question_type.value} questions require manual grading")
