import pytest
from pydantic import ValidationError

from app.schemas.bloom import BloomLevel
from app.schemas.constraints import BloomDistribution, PaperConstraints
from app.schemas.question import Question, QuestionType
from app.schemas.topic import Topic


def test_bloom_level_ordering():
    assert BloomLevel.REMEMBER < BloomLevel.UNDERSTAND < BloomLevel.CREATE


def test_topic_defaults():
    t = Topic(id="t1", name="Recursion")
    assert t.prerequisite_ids == []
    assert t.importance_score is None


def test_question_defaults():
    q = Question(
        id="q1", text="test?", question_type=QuestionType.SHORT_ANSWER, marks=5, bloom_level=BloomLevel.UNDERSTAND
    )
    assert q.topic_ids == []
    assert q.created_at is not None


def test_bloom_distribution_must_sum_to_one():
    BloomDistribution(weights={BloomLevel.REMEMBER: 0.5, BloomLevel.UNDERSTAND: 0.5})  # ok

    with pytest.raises(ValidationError):
        BloomDistribution(weights={BloomLevel.REMEMBER: 0.5, BloomLevel.UNDERSTAND: 0.2})


def test_paper_constraints_defaults():
    pc = PaperConstraints(
        total_marks=50, bloom_distribution=BloomDistribution(weights={BloomLevel.REMEMBER: 1.0})
    )
    assert pc.total_marks == 50
    assert pc.co_coverage == {}
    assert pc.num_questions is None
