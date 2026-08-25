from pydantic import BaseModel


class TestCaseResult(BaseModel):
    input: str
    expected_output: str
    actual_output: str
    passed: bool
    error: str | None = None


class GradeResult(BaseModel):
    correct: bool
    marks_awarded: int
    max_marks: int
    detail: str
    test_results: list[TestCaseResult] | None = None
