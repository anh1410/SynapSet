"""Deterministic checks on the eval golden dataset and its helpers. No network, so these run in the default suite."""

import pytest

from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from evals.dataset import GoldenCase, load_golden_dataset, render_question, structural_problems

CASES = load_golden_dataset()


def make_case(**overrides) -> GoldenCase:
    defaults = dict(
        id="case", topic="Topic", bloom_level="UNDERSTAND", question_type="short_answer", marks=5, syllabus="text"
    )
    return GoldenCase(**{**defaults, **overrides})


def make_question(**overrides) -> Question:
    defaults = dict(
        id="q",
        text="Explain the topic.",
        question_type=QuestionType.SHORT_ANSWER,
        marks=5,
        bloom_level=BloomLevel.UNDERSTAND,
        correct_answer="Because of the topic.",
    )
    return Question(**{**defaults, **overrides})


def test_golden_dataset_size_is_in_range():
    assert 20 <= len(CASES) <= 30


def test_golden_case_ids_and_topics_are_unique():
    assert len({c.id for c in CASES}) == len(CASES)
    assert len({c.topic for c in CASES}) == len(CASES)


def test_golden_dataset_uses_valid_enums():
    for case in CASES:
        assert case.bloom_level in BloomLevel.__members__
        QuestionType(case.question_type)


def test_golden_dataset_covers_every_bloom_level_and_several_question_types():
    assert {c.bloom_level for c in CASES} == set(BloomLevel.__members__)
    assert len({c.question_type for c in CASES}) >= 4


def test_golden_syllabi_have_enough_text_to_ground_a_question():
    for case in CASES:
        assert len(case.syllabus) >= 300, case.id


def test_golden_prerequisites_refer_to_topics_in_the_dataset():
    topics = {c.topic for c in CASES}
    for case in CASES:
        assert set(case.prerequisites) <= topics, case.id


def test_structural_problems_accepts_a_well_formed_question():
    assert structural_problems(make_case(), make_question()) == []


def test_structural_problems_flags_wrong_marks_type_and_bloom():
    question = make_question(marks=10, question_type=QuestionType.LONG_ANSWER, bloom_level=BloomLevel.APPLY)
    problems = structural_problems(make_case(), question)
    assert len(problems) == 3


def test_structural_problems_flags_mcq_with_wrong_option_count_or_answer():
    case = make_case(question_type="mcq", marks=1)
    question = make_question(
        question_type=QuestionType.MCQ, marks=1, options=["a", "b", "c"], correct_answer="d"
    )
    problems = structural_problems(case, question)
    assert any("expected 4 options" in p for p in problems)
    assert any("not one of the options" in p for p in problems)


def test_structural_problems_flags_fill_in_blank_without_placeholder():
    case = make_case(question_type="fill_in_blank", marks=1)
    question = make_question(
        text="The capital of France is Paris.",
        question_type=QuestionType.FILL_IN_BLANK,
        marks=1,
        options=["Paris", "Lyon", "Nice", "Rome"],
        correct_answer="Paris",
    )
    assert any("placeholder" in p for p in structural_problems(case, question))


def test_structural_problems_flags_missing_model_answer():
    assert "missing model answer" in structural_problems(make_case(), make_question(correct_answer=None))


@pytest.mark.parametrize("fragment", ["Question: Explain the topic.", "Model answer: Because of the topic."])
def test_render_question_includes_question_and_answer(fragment):
    assert fragment in render_question(make_question())


def test_render_question_lists_options():
    rendered = render_question(make_question(options=["x", "y"]))
    assert "- x" in rendered and "- y" in rendered
