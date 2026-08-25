from app.schemas.bloom import BloomLevel
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
