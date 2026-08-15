from app.schemas.bloom import BloomLevel
from app.schemas.constraints import BloomDistribution, PaperConstraints
from app.schemas.question import Question, QuestionType
from app.services.paper_optimization import optimize_paper


def _q(qid, marks, bloom, topics=None, co_ids=None, qtype=QuestionType.SHORT_ANSWER, unit=None):
    return Question(
        id=qid,
        text=f"question {qid}",
        question_type=qtype,
        marks=marks,
        bloom_level=bloom,
        topic_ids=topics or [],
        co_ids=co_ids or [],
        unit=unit,
    )


def test_optimize_exact_total_marks():
    candidates = [_q("1", 5, BloomLevel.UNDERSTAND), _q("2", 5, BloomLevel.UNDERSTAND), _q("3", 10, BloomLevel.ANALYZE)]
    constraints = PaperConstraints(
        total_marks=10, bloom_distribution=BloomDistribution(weights={BloomLevel.UNDERSTAND: 1.0})
    )
    result = optimize_paper(candidates, constraints)
    assert result.status == "OPTIMAL"
    assert sum(q.marks for q in result.selected) == 10


def test_optimize_infeasible():
    candidates = [_q("1", 5, BloomLevel.UNDERSTAND)]
    constraints = PaperConstraints(
        total_marks=100, bloom_distribution=BloomDistribution(weights={BloomLevel.UNDERSTAND: 1.0})
    )
    result = optimize_paper(candidates, constraints)
    assert result.status == "INFEASIBLE"
    assert result.selected == []


def test_optimize_co_coverage_enforced():
    candidates = [
        _q("1", 5, BloomLevel.UNDERSTAND, co_ids=["CO1"]),
        _q("2", 5, BloomLevel.UNDERSTAND, co_ids=[]),
    ]
    constraints = PaperConstraints(
        total_marks=5,
        bloom_distribution=BloomDistribution(weights={BloomLevel.UNDERSTAND: 1.0}),
        co_coverage={"CO1": 1},
    )
    result = optimize_paper(candidates, constraints)
    assert result.status == "OPTIMAL"
    assert any("CO1" in q.co_ids for q in result.selected)


def test_optimize_num_questions_constraint():
    candidates = [_q(str(i), 1, BloomLevel.REMEMBER) for i in range(5)]
    constraints = PaperConstraints(
        total_marks=3,
        num_questions=3,
        bloom_distribution=BloomDistribution(weights={BloomLevel.REMEMBER: 1.0}),
    )
    result = optimize_paper(candidates, constraints)
    assert result.status == "OPTIMAL"
    assert len(result.selected) == 3
