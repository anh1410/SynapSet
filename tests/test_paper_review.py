"""Final-paper review: blueprint / CO maths, replacement candidates,
constraint-preserving regeneration, marks edits, locking, and isolation."""

from datetime import timedelta

import pytest

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from tests.conftest import T0
from tests.factories import make_exam, other_teacher_headers, q, seed, seed_graph, small_pattern, submit

MCQ, SA = QuestionType.MCQ, QuestionType.SHORT_ANSWER


@pytest.fixture
def paper(api_client, clock):
    """A compliant 14-mark pattern paper (4 x 1-mark MCQ + 2 x 5-mark) plus spare bank questions."""
    seed_graph(api_client, {"stacks": "Stacks", "queues": "Queues", "recursion": "Recursion"}, prereqs=[("stacks", "recursion")])
    seed(api_client, [
        q("a1", MCQ, 1, BloomLevel.REMEMBER, ["stacks"], co_ids=["CO1"]),
        q("a2", MCQ, 1, BloomLevel.REMEMBER, ["queues"], co_ids=["CO1"]),
        q("a3", MCQ, 1, BloomLevel.UNDERSTAND, ["stacks"]),
        q("a4", MCQ, 1, BloomLevel.UNDERSTAND, ["queues"]),
        q("b1", SA, 5, BloomLevel.APPLY, ["recursion"], difficulty=6.0, co_ids=["CO2"]),
        q("b2", SA, 5, BloomLevel.ANALYZE, ["stacks"], difficulty=8.5, co_ids=["CO2"]),
        # spares
        q("b3", SA, 5, BloomLevel.APPLY, ["recursion"], difficulty=6.2, co_ids=["CO2"]),  # exact twin of b1
        q("b4", SA, 5, BloomLevel.REMEMBER, ["queues"], difficulty=2.0),  # same marks, different everything
        q("a5", MCQ, 1, BloomLevel.REMEMBER, ["stacks"]),
    ])
    pid = small_pattern(api_client, co_requirements=[
        {"co_code": "CO1", "min_questions": 2},
        {"co_code": "CO2", "min_percent": 30},
    ])
    exam_id = make_exam(api_client, ["a1", "a2", "a3", "a4", "b1", "b2"], pattern_id=pid, exam_type="MSE")
    return exam_id, pid


def _bp(api_client, exam_id, ids=None):
    r = api_client.post(f"/api/v1/exams/{exam_id}/blueprint", json={"question_ids": ids})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- blueprint / CO analysis ----------


def test_blueprint_reports_targets_actuals_and_co_percent(api_client, paper):
    exam_id, _ = paper
    bp = _bp(api_client, exam_id)
    assert bp["compliant"] is True
    assert bp["total_marks"] == 14 and bp["target_marks"] == 14
    assert [s["filled"] for s in bp["sections"]] == [4, 2]
    cos = {c["co_code"]: c for c in bp["course_outcomes"]}
    # CO2: b1 + b2 = 10 of 14 marks = 71.4% >= 30% target
    assert cos["CO2"]["actual_percent"] == 71.4 and cos["CO2"]["min_percent"] == 30 and cos["CO2"]["met"]
    assert cos["CO1"]["actual"] == 2 and cos["CO1"]["met"]
    types = {r["key"]: r["actual_marks"] for r in bp["question_types"]}
    assert types == {"mcq": 4, "short_answer": 10}
    skills = {r["key"]: r["actual_marks"] for r in bp["skills"]}
    assert skills == {"conceptual": 4, "reasoning": 10}
    assert {r["label"] for r in bp["topics"]} == {"Stacks", "Queues", "Recursion"}


def test_blueprint_topics_split_marks_and_skip_course_outcome_nodes(api_client, clock):
    from app.core.graph_store import get_graph_store

    seed_graph(api_client, {"stacks": "Stacks", "queues": "Queues", "co1": "CO1"})
    gs = get_graph_store(api_client.subject_id)
    gs.add_relation("stacks", "co1", "MAPS_TO")
    gs.save()
    seed(api_client, [q("t1", SA, 5, topics=["stacks", "queues", "co1"]), q("t2", SA, 5, topics=["stacks"])])
    bp = _bp(api_client, make_exam(api_client, ["t1", "t2"]))
    topics = {r["label"]: r["actual_marks"] for r in bp["topics"]}
    assert topics == {"Stacks": 7.5, "Queues": 2.5}


def test_co_percent_target_flagged_when_not_met(api_client, paper):
    exam_id, _ = paper
    # One CO2 question left: 5 of 14 marks = 35.7% - still above the 30% target.
    bp = _bp(api_client, exam_id, ["a1", "a2", "a3", "a4", "b4", "b3"])
    cos = {c["co_code"]: c for c in bp["course_outcomes"]}
    assert cos["CO2"]["actual_percent"] == 35.7 and cos["CO2"]["met"]
    # No CO2 questions at all: 0% of marks, flagged.
    bp = _bp(api_client, exam_id, ["a1", "a2", "a3", "a4", "b4"])
    assert bp["compliant"] is False
    assert any("CO2" in i and "needs at least 30%" in i for i in bp["issues"])


def test_co_requirement_needs_a_target(api_client, clock):
    r = api_client.post("/api/v1/patterns", json={
        "subject_id": api_client.subject_id, "name": "X", "exam_type": "MSE", "total_marks": 5, "duration_minutes": 10,
        "sections": [{"name": "A", "num_questions": 1, "marks_per_question": 5}],
        "co_requirements": [{"co_code": "CO9"}],
    })
    assert r.status_code == 422


def test_blueprint_for_free_form_quiz_has_no_targets(api_client, clock):
    seed(api_client, [q("x1", MCQ, 2, BloomLevel.REMEMBER), q("x2", SA, 3, BloomLevel.APPLY)])
    exam_id = make_exam(api_client, ["x1", "x2"])
    bp = _bp(api_client, exam_id)
    assert bp["compliant"] is None and bp["pattern_id"] is None and bp["sections"] == []
    assert {r["label"]: r["actual_percent"] for r in bp["bloom"]} == {"Remember": 40.0, "Apply": 60.0}
    assert all(r["target_percent"] is None for r in bp["bloom"])


# ---------- editing: reorder / remove / replace ----------


def test_reorder_keeps_compliance_and_remove_breaks_it(api_client, paper):
    exam_id, _ = paper
    assert _bp(api_client, exam_id, ["b2", "b1", "a4", "a3", "a2", "a1"])["compliant"] is True
    removed = _bp(api_client, exam_id, ["a1", "a2", "a3", "a4", "b1"])
    assert removed["compliant"] is False
    assert any("Part B: 1 of 2" in i for i in removed["issues"])


def test_replacement_candidates_rank_compliant_twins_first(api_client, paper):
    exam_id, _ = paper
    r = api_client.post(f"/api/v1/exams/{exam_id}/review/candidates", json={"target_id": "b1"})
    assert r.status_code == 200, r.text
    cands = r.json()
    ids = [c["question"]["id"] for c in cands]
    assert ids[0] == "b3"  # same type, bloom, difficulty, topic
    assert cands[0]["keeps_compliant"] is True
    assert set(cands[0]["matches"]) >= {"type", "bloom", "difficulty", "topic"}
    assert "a5" not in ids  # wrong marks for the slot
    b4 = next(c for c in cands if c["question"]["id"] == "b4")
    assert set(b4["matches"]) == {"type"}


def test_replacement_that_breaks_pattern_is_reported(api_client, clock):
    seed_graph(api_client, {"stacks": "Stacks"})
    seed(api_client, [
        *(q(f"a{i}", MCQ, 1, BloomLevel.REMEMBER, ["stacks"]) for i in range(4)),
        q("b1", SA, 5, BloomLevel.APPLY, ["stacks"], co_ids=["CO2"]),
        q("b2", SA, 5, BloomLevel.APPLY, ["stacks"], co_ids=["CO2"]),
        q("plain", SA, 5, BloomLevel.APPLY, ["stacks"]),  # no CO tag
    ])
    pid = small_pattern(api_client, co_requirements=[{"co_code": "CO2", "min_questions": 2}])
    exam_id = make_exam(api_client, ["a0", "a1", "a2", "a3", "b1", "b2"], pattern_id=pid)
    cands = api_client.post(f"/api/v1/exams/{exam_id}/review/candidates", json={"target_id": "b1"}).json()
    plain = next(c for c in cands if c["question"]["id"] == "plain")
    assert plain["keeps_compliant"] is False
    assert plain["new_issues"] == ["CO2: 1 of at least 2 question(s)"]


def test_draft_with_foreign_question_rejected(api_client, paper):
    exam_id, _ = paper
    r = api_client.post(f"/api/v1/exams/{exam_id}/blueprint", json={"question_ids": ["a1", "not-in-bank"]})
    assert r.status_code == 422


# ---------- regeneration ----------


def _no_gemini(monkeypatch):
    def boom(**_):
        raise AssertionError("generator must not be called when a bank question fits")

    monkeypatch.setattr("app.api.paper_review.generate_questions", boom)


def test_regenerate_reuses_matching_bank_question_without_gemini(api_client, paper, monkeypatch):
    exam_id, _ = paper
    _no_gemini(monkeypatch)
    r = api_client.post(f"/api/v1/exams/{exam_id}/review/regenerate", json={"target_id": "b1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "reused" and body["question"]["id"] == "b3"
    assert body["all_constraints_met"] is True
    assert {c["name"] for c in body["checks"]} >= {"Question type", "Marks", "Bloom's level", "Difficulty", "Topic"}


def test_regenerate_generates_with_pinned_constraints(api_client, paper, monkeypatch):
    exam_id, _ = paper
    calls = []

    def fake_generate(**kw):
        calls.append(kw)
        # Deliberately "wrong" marks/bloom from the model, and no topic tags - the endpoint must pin them.
        return [q("fresh", SA, 9, BloomLevel.CREATE, [], difficulty=None, text="A brand new question on recursion?")]

    monkeypatch.setattr("app.api.paper_review.generate_questions", fake_generate)
    monkeypatch.setattr("app.api.paper_review.score_difficulty", lambda qq, gs: type("D", (), {"score": 6.5})())
    r = api_client.post(f"/api/v1/exams/{exam_id}/review/regenerate", json={"target_id": "b1", "force_new": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "generated"
    assert calls[0]["topic"] == "Recursion" and calls[0]["marks"] == 5
    assert calls[0]["bloom_level"] == BloomLevel.APPLY and calls[0]["question_type"] == SA
    new = body["question"]
    assert new["marks"] == 5 and new["bloom_level"] == int(BloomLevel.APPLY)
    assert "recursion" in new["topic_ids"] and new["co_ids"] == ["CO2"]
    assert body["all_constraints_met"] is True
    # Saved to the bank; the paper itself is untouched until the teacher saves.
    assert api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}").json()[-1]["id"] == "fresh"
    assert "fresh" not in api_client.get(f"/api/v1/exams/{exam_id}").json()["exam"]["question_ids"]
    # And swapping it in keeps the paper compliant.
    assert _bp(api_client, exam_id, ["a1", "a2", "a3", "a4", "fresh", "b2"])["compliant"] is True


def test_regenerate_retries_once_for_difficulty_band_and_reports_miss(api_client, paper, monkeypatch):
    exam_id, _ = paper
    calls = []
    monkeypatch.setattr("app.api.paper_review.generate_questions",
                        lambda **kw: calls.append(kw) or [q(f"g{len(calls)}", SA, 5, BloomLevel.APPLY, ["recursion"])])
    monkeypatch.setattr("app.api.paper_review.score_difficulty", lambda qq, gs: type("D", (), {"score": 9.5})())
    body = api_client.post(f"/api/v1/exams/{exam_id}/review/regenerate", json={"target_id": "b1", "force_new": True}).json()
    assert len(calls) == 2  # one retry for the difficulty band, no more
    diff = next(c for c in body["checks"] if c["name"] == "Difficulty")
    assert diff["required"] == "medium" and diff["actual"] == "hard" and not diff["ok"]
    assert body["all_constraints_met"] is False


def test_regenerate_retries_when_result_just_rephrases_original(api_client, paper, monkeypatch):
    exam_id, _ = paper
    outputs = [
        q("same", SA, 5, BloomLevel.APPLY, ["recursion"], text="Question b1?"),  # a rephrase of the original
        q("diff", SA, 5, BloomLevel.APPLY, ["recursion"], text="Compare the time complexity of merge sort and bubble sort on large inputs."),
    ]
    monkeypatch.setattr("app.api.paper_review.generate_questions", lambda **kw: [outputs.pop(0)])
    monkeypatch.setattr("app.api.paper_review.score_difficulty", lambda qq, gs: type("D", (), {"score": 6.0})())
    body = api_client.post(f"/api/v1/exams/{exam_id}/review/regenerate", json={"target_id": "b1", "force_new": True}).json()
    assert outputs == []  # the retry was used
    assert body["question"]["id"] == "diff"
    assert "very similar" not in body["note"]


# ---------- marks ----------


def test_marks_edit_in_place_when_unshared(api_client, paper):
    exam_id, _ = paper
    r = api_client.post(f"/api/v1/exams/{exam_id}/review/marks", json={"target_id": "b1", "marks": 6})
    assert r.status_code == 200
    assert r.json()["copied"] is False and r.json()["question"]["marks"] == 6
    bp = _bp(api_client, exam_id)
    assert bp["compliant"] is False  # 6 marks no longer fits a 5-mark slot - and it's reported
    assert any("Part B" in i for i in bp["issues"])


def test_unsaved_marks_edits_are_draft_only(api_client, paper):
    exam_id, _ = paper
    r = api_client.post(f"/api/v1/exams/{exam_id}/blueprint", json={
        "question_ids": ["a1", "a2", "a3", "a4", "b1", "b2"], "marks_overrides": {"a4": 2}})
    bp = r.json()
    assert bp["total_marks"] == 15 and bp["compliant"] is False
    assert any("Part A: 3 of 4" in i for i in bp["issues"])
    # Nothing was written: the bank and the saved paper are unchanged.
    bank = {x["id"]: x for x in api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}").json()}
    assert bank["a4"]["marks"] == 1
    assert _bp(api_client, exam_id)["compliant"] is True
    bad = api_client.post(f"/api/v1/exams/{exam_id}/blueprint", json={"question_ids": ["a1"], "marks_overrides": {"a1": 0}})
    assert bad.status_code == 422


def test_marks_edit_copies_question_used_elsewhere(api_client, paper):
    exam_id, _ = paper
    make_exam(api_client, ["b1"], name="Other quiz")
    body = api_client.post(f"/api/v1/exams/{exam_id}/review/marks", json={"target_id": "b1", "marks": 4}).json()
    assert body["copied"] is True
    assert body["question"]["id"] != "b1" and body["question"]["derived_from"] == "b1"
    bank = {x["id"]: x for x in api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}").json()}
    assert bank["b1"]["marks"] == 5  # original untouched


# ---------- locking + isolation ----------


def test_paper_locked_once_students_submit(api_client, clock):
    seed(api_client, [q("m1", MCQ, 1, BloomLevel.REMEMBER), q("m2", MCQ, 1, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=5))
    submit(api_client, exam_id, "Asha", "R1", {"m1": "right"})
    r = api_client.patch(f"/api/v1/exams/{exam_id}", json={"question_ids": ["m2"]})
    assert r.status_code == 409
    assert api_client.post(f"/api/v1/exams/{exam_id}/review/marks", json={"target_id": "m1", "marks": 3}).status_code == 409
    # Non-paper edits (e.g. closing time) still work.
    assert api_client.patch(f"/api/v1/exams/{exam_id}", json={"closes_at": (T0 + timedelta(days=1)).isoformat()}).status_code == 200


def test_review_endpoints_isolated_between_teachers(api_client, paper):
    exam_id, _ = paper
    h = other_teacher_headers(api_client)
    assert api_client.post(f"/api/v1/exams/{exam_id}/blueprint", json={}, headers=h).status_code == 404
    assert api_client.post(f"/api/v1/exams/{exam_id}/review/candidates", json={"target_id": "b1"}, headers=h).status_code == 404
    assert api_client.post(f"/api/v1/exams/{exam_id}/review/regenerate", json={"target_id": "b1"}, headers=h).status_code == 404
    assert api_client.post(f"/api/v1/exams/{exam_id}/review/marks", json={"target_id": "b1", "marks": 2}, headers=h).status_code == 404
    assert api_client.get(f"/api/v1/exams/{exam_id}/export/paper", headers=h).status_code == 404
