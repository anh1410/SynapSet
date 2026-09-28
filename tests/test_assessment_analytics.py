"""Assessment-level analytics, insufficient-data handling, and weak-topic
detection (coverage risk vs performance risk)."""

from datetime import timedelta

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from tests.conftest import T0
from tests.factories import make_exam, other_teacher_headers, q, seed, seed_graph, submit

MCQ = QuestionType.MCQ


def _analytics(api_client, exam_id):
    r = api_client.get(f"/api/v1/analytics/exams/{exam_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _quiz(api_client, predicted: dict[str, float]):
    seed_graph(api_client, {"stacks": "Stacks", "queues": "Queues", "trees": "Trees", "graphs": "Graphs"})
    topics = {"easy1": "stacks", "easy2": "queues", "hard1": "trees", "hard2": "graphs"}
    seed(api_client, [q(k, MCQ, 2, BloomLevel.REMEMBER if "easy" in k else BloomLevel.ANALYZE, [topics[k]], difficulty=v)
                      for k, v in predicted.items()])
    return make_exam(api_client, list(predicted), go_live=T0 - timedelta(minutes=1))


def test_small_class_reports_not_enough_data(api_client, clock):
    exam_id = _quiz(api_client, {"easy1": 2.0, "easy2": 3.0, "hard1": 8.0, "hard2": 9.0})
    submit(api_client, exam_id, "A", "R1", {"easy1": "right", "easy2": "right", "hard1": "wrong", "hard2": "wrong"})
    a = _analytics(api_client, exam_id)
    assert a["summary"]["students"] == 1 and a["participation"]["submitted"] == 1
    assert a["min_responses"] == 5
    for qs in a["questions"]:
        assert qs["responses"] == 1 and qs["sufficient"] is False and qs["calibration_flag"] is None
    assert a["calibration"]["status"] == "insufficient"
    assert "Not enough data" in a["calibration"]["note"]


def test_question_stats_and_difficulty_calibration(api_client, clock):
    exam_id = _quiz(api_client, {"easy1": 2.0, "easy2": 3.0, "hard1": 8.0, "hard2": 9.0})
    # Five students: easy questions mostly right, hard ones mostly wrong -
    # except easy2, which everyone gets wrong (harder than predicted).
    for i in range(5):
        submit(api_client, exam_id, f"S{i}", f"R{i}", {
            "easy1": "right",
            "easy2": "wrong",
            "hard1": "right" if i == 0 else "wrong",
            "hard2": "wrong",
        })
    a = _analytics(api_client, exam_id)
    stats = {s["question_id"]: s for s in a["questions"]}
    assert [s["position"] for s in a["questions"]] == [1, 2, 3, 4]
    assert stats["easy1"]["average_percent"] == 100.0 and stats["easy1"]["sufficient"] is True
    assert stats["easy1"]["predicted_bucket"] == "easy" and stats["easy1"]["calibration_flag"] is None
    assert stats["easy2"]["calibration_flag"] == "harder_than_predicted"
    assert stats["hard1"]["average_percent"] == 20.0 and stats["hard1"]["topics"] == ["Trees"]
    assert a["calibration"]["status"] == "ok" and a["calibration"]["questions_used"] == 4
    assert a["calibration"]["spearman"] is not None
    # Reuses the class breakdowns: Bloom's, topics, skills.
    assert {r["label"] for r in a["breakdowns"]["bloom"]} == {"Remember", "Analyze"}
    assert a["summary"]["average_percent"] == 30.0
    assert sum(g["count"] for g in a["grade_distribution"]) == 5


def test_participation_counts_attempts(api_client, clock):
    seed(api_client, [q("t1", MCQ, 1)])
    exam_id = make_exam(api_client, ["t1"], go_live=T0 - timedelta(minutes=1), duration=10)
    a1 = api_client.post(f"/api/v1/exams/{exam_id}/start", json={"student_name": "A", "student_identifier": "1"}).json()
    api_client.post(f"/api/v1/exams/{exam_id}/start", json={"student_name": "B", "student_identifier": "2"})
    api_client.post(f"/api/v1/exams/{exam_id}/submit", json={
        "student_name": "A", "attempt_id": a1["attempt"]["attempt_id"], "answers": [{"question_id": "t1", "answer": "right"}]})
    clock.advance(minutes=30)
    p = _analytics(api_client, exam_id)["participation"]
    assert p == {"started": 2, "submitted": 1, "in_progress": 0, "timed_out": 1, "auto_submitted": 0}


def test_topic_risk_separates_coverage_from_performance(api_client, clock):
    seed_graph(api_client, {"arrays": "Arrays", "stacks": "Stacks", "trees": "Trees", "graphs": "Graphs"})
    seed(api_client, [
        *(q(f"arr{i}", MCQ, 1, topics=["arrays"]) for i in range(3)),  # well covered, done well
        *(q(f"stk{i}", MCQ, 1, topics=["stacks"]) for i in range(3)),  # well covered, done badly
        q("tree0", MCQ, 1, topics=["trees"]),  # thin coverage
    ])  # graphs: no questions at all
    exam_id = make_exam(api_client, ["arr0", "arr1", "stk0", "stk1", "tree0"], go_live=T0 - timedelta(minutes=1))
    for i in range(3):
        submit(api_client, exam_id, f"S{i}", f"R{i}",
               {"arr0": "right", "arr1": "right", "stk0": "wrong", "stk1": "right" if i == 0 else "wrong", "tree0": "right"})
    r = api_client.get(f"/api/v1/analytics/topic-risk?subject_id={api_client.subject_id}")
    assert r.status_code == 200, r.text
    risk = r.json()
    assert risk["min_questions"] == 3 and risk["risk_percent"] == 50.0 and risk["min_answers"] == 2
    rows = {x["topic_id"]: x for x in risk["rows"]}
    assert rows["arrays"]["coverage"] == "good" and rows["arrays"]["performance"] == "good" and rows["arrays"]["percent"] == 100.0
    assert rows["stacks"]["coverage"] == "good" and rows["stacks"]["performance"] == "at_risk"
    assert rows["trees"]["coverage"] == "low" and rows["trees"]["performance"] == "good"
    assert rows["graphs"]["coverage"] == "none" and rows["graphs"]["performance"] == "insufficient"
    assert [x["topic_id"] for x in risk["performance_risks"]] == ["stacks"]
    assert {x["topic_id"] for x in risk["coverage_risks"]} == {"trees", "graphs"}


def test_course_outcome_nodes_are_not_topics(api_client, clock):
    from app.core.graph_store import get_graph_store

    seed_graph(api_client, {"stacks": "Stacks", "co1": "CO1"})
    gs = get_graph_store(api_client.subject_id)
    gs.add_relation("stacks", "co1", "MAPS_TO")
    gs.save()
    rows = api_client.get(f"/api/v1/analytics/topic-risk?subject_id={api_client.subject_id}").json()["rows"]
    assert [r["topic_id"] for r in rows] == ["stacks"]


def test_course_outcome_nodes_excluded_from_topic_analytics_and_graph_coverage(api_client, clock):
    """Regression: questions the generator tagged with a CO node made "CO2" show
    up as a topic (even as a strength) and CO nodes counted as neglected topics."""
    from app.core.graph_store import get_graph_store

    seed_graph(api_client, {"stacks": "Stacks", "co2": "CO2"})
    gs = get_graph_store(api_client.subject_id)
    gs.add_relation("stacks", "co2", "MAPS_TO")
    gs.save()
    seed(api_client, [q("c1", MCQ, 1, topics=["stacks", "co2"]), q("c2", MCQ, 1, topics=["stacks", "co2"])])
    exam_id = make_exam(api_client, ["c1", "c2"], go_live=T0 - timedelta(minutes=1))
    for i in range(2):
        submit(api_client, exam_id, f"S{i}", f"R{i}", {"c1": "right", "c2": "right"})

    ov = api_client.get(f"/api/v1/analytics/overview?subject_id={api_client.subject_id}").json()
    assert [t["key"] for t in ov["breakdowns"]["topics"]] == ["stacks"]
    assert [t["key"] for t in ov["breakdowns"]["strengths"]] == ["stacks"]
    ea = api_client.get(f"/api/v1/analytics/exams/{exam_id}").json()
    assert ea["questions"][0]["topics"] == ["Stacks"]
    key = ov["students"][0]["key"]
    sd = api_client.get(f"/api/v1/analytics/students/{key}?subject_id={api_client.subject_id}").json()
    assert [t["key"] for t in sd["breakdowns"]["topics"]] == ["stacks"]

    nodes = {n["id"]: n for n in api_client.get(f"/api/v1/graph?subject_id={api_client.subject_id}").json()["nodes"]}
    assert nodes["co2"]["is_course_outcome"] is True and nodes["co2"]["neglected"] is False
    assert nodes["stacks"]["is_course_outcome"] is False and nodes["stacks"]["coverage_pct"] == 100


def test_topic_with_too_few_answers_is_not_called_a_risk(api_client, clock):
    seed_graph(api_client, {"stacks": "Stacks"})
    seed(api_client, [q("s0", MCQ, 1, topics=["stacks"])])
    exam_id = make_exam(api_client, ["s0"], go_live=T0 - timedelta(minutes=1))
    submit(api_client, exam_id, "A", "R1", {"s0": "wrong"})  # one wrong answer is not a trend
    rows = {x["topic_id"]: x for x in api_client.get(f"/api/v1/analytics/topic-risk?subject_id={api_client.subject_id}").json()["rows"]}
    assert rows["stacks"]["performance"] == "insufficient" and rows["stacks"]["percent"] == 0.0


def test_thresholds_are_configurable(api_client, clock, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "topic_min_questions", 1)
    seed_graph(api_client, {"trees": "Trees"})
    seed(api_client, [q("tree0", MCQ, 1, topics=["trees"])])
    rows = api_client.get(f"/api/v1/analytics/topic-risk?subject_id={api_client.subject_id}").json()["rows"]
    assert rows[0]["coverage"] == "good"


def test_assessment_analytics_isolated_between_teachers(api_client, clock):
    seed(api_client, [q("i1", MCQ, 1)])
    exam_id = make_exam(api_client, ["i1"], go_live=T0 - timedelta(minutes=1))
    h = other_teacher_headers(api_client)
    assert api_client.get(f"/api/v1/analytics/exams/{exam_id}", headers=h).status_code == 404
    assert api_client.get(f"/api/v1/analytics/topic-risk?subject_id={api_client.subject_id}", headers=h).status_code == 404
