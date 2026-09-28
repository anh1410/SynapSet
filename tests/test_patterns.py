import pytest
from pydantic import ValidationError

from app.schemas.bloom import BloomLevel
from app.schemas.exam_pattern import ExamPatternFields, PatternSection, pattern_presets
from app.schemas.question import Question, QuestionType
from app.services.pattern_assembly import (
    TopicInfo,
    assemble,
    evaluate_selection,
    plan_gap_requests,
    question_unit,
)


def _q(qid, qtype, marks, bloom, topics=(), difficulty=5.0, co_ids=()):
    return Question(
        id=qid,
        text=f"Question {qid}",
        question_type=qtype,
        marks=marks,
        bloom_level=bloom,
        topic_ids=list(topics),
        co_ids=list(co_ids),
        difficulty_score=difficulty,
    )


def _small_pattern(**overrides) -> ExamPatternFields:
    data = dict(
        name="Mini MSE",
        exam_type="MSE",
        total_marks=14,
        duration_minutes=60,
        sections=[
            PatternSection(name="Part A", num_questions=4, marks_per_question=1, question_types=[QuestionType.MCQ]),
            PatternSection(name="Part B", num_questions=2, marks_per_question=5),
        ],
    )
    data.update(overrides)
    return ExamPatternFields(**data)


def _bank():
    bank = [_q(f"a{i}", QuestionType.MCQ, 1, BloomLevel.REMEMBER, [f"t{i}"], difficulty=3) for i in range(6)]
    bank += [
        _q("b1", QuestionType.SHORT_ANSWER, 5, BloomLevel.APPLY, ["t1", "t7"], difficulty=6),
        _q("b2", QuestionType.LONG_ANSWER, 5, BloomLevel.ANALYZE, ["t8"], difficulty=8.5),
        _q("b3", QuestionType.SHORT_ANSWER, 5, BloomLevel.UNDERSTAND, ["t2"], difficulty=5),
        _q("wrong-marks", QuestionType.SHORT_ANSWER, 3, BloomLevel.APPLY, ["t9"]),
    ]
    return bank


# ---------- schema validation ----------


def test_presets_are_valid_and_cover_mse_and_see():
    presets = pattern_presets()
    assert {p.exam_type for p in presets} == {"MSE", "SEE"}
    for p in presets:
        assert sum(s.total_marks for s in p.sections) == p.total_marks


def test_section_marks_must_add_up_to_total():
    with pytest.raises(ValidationError, match="Sections add up to 14"):
        _small_pattern(total_marks=20)


def test_distribution_must_add_up_to_100():
    with pytest.raises(ValidationError, match="adds up to 90"):
        _small_pattern(bloom_distribution=[{"bloom_level": 1, "percent": 50}, {"bloom_level": 3, "percent": 40}])


def test_duplicate_units_rejected():
    with pytest.raises(ValidationError, match="Unit numbers must be unique"):
        _small_pattern(units=[{"unit": 1, "percent": 50}, {"unit": 1, "percent": 50}])


# ---------- assembly ----------


def test_assemble_fills_every_section_with_matching_questions():
    pattern = _small_pattern()
    result = assemble(pattern, _bank())
    assert result.satisfied
    assert result.status == "optimal"
    report = result.report
    assert report.actual_marks == 14
    assert [s.filled for s in report.sections] == [4, 2]
    assert "wrong-marks" not in result.question_ids
    part_a = set(report.sections[0].question_ids)
    assert all(qid.startswith("a") for qid in part_a)


def test_assemble_respects_bloom_distribution():
    # Part B must be all higher-order: 10 of 14 marks at Apply/Analyze.
    pattern = _small_pattern(
        bloom_distribution=[
            {"bloom_level": 1, "percent": 28.6},
            {"bloom_level": 3, "percent": 35.7},
            {"bloom_level": 4, "percent": 35.7},
        ],
        tolerance_percent=5,
    )
    result = assemble(pattern, _bank())
    assert result.satisfied
    assert set(result.report.sections[1].question_ids) == {"b1", "b2"}


def test_assemble_maximizes_topic_coverage():
    result = assemble(_small_pattern(), _bank())
    # 4 MCQs on distinct topics + two 5-markers; b1 covers two topics.
    assert result.report.topics_covered >= 6


def test_assemble_reports_section_shortfall_and_returns_draft():
    bank = [q for q in _bank() if q.marks != 5]
    result = assemble(_small_pattern(), bank)
    assert not result.satisfied
    assert result.status == "infeasible"
    assert result.blocking == ["sections"]
    assert result.report.sections[0].filled == 4  # the part that *can* be filled still is
    assert result.report.sections[1].eligible_in_pool == 0
    assert any("Part B" in issue for issue in result.report.issues)


def test_assemble_identifies_blocking_distribution():
    # Asks for 30% Evaluate, which nothing in the bank is.
    pattern = _small_pattern(
        bloom_distribution=[{"bloom_level": 1, "percent": 30}, {"bloom_level": 3, "percent": 40}, {"bloom_level": 5, "percent": 30}]
    )
    result = assemble(pattern, _bank())
    assert not result.satisfied
    assert result.blocking == ["bloom"]
    assert "bloom" in result.relaxed
    assert len(result.question_ids) == 6  # sections still filled in the draft


def test_units_map_questions_through_knowledge_graph_topics():
    pattern = _small_pattern(
        units=[{"unit": 1, "topic_ids": ["t0", "t1", "t2", "t7"], "percent": 60}, {"unit": 2, "topic_ids": ["t3", "t8"], "percent": 40}]
    )
    bank = _bank()
    by_id = {q.id: q for q in bank}
    assert question_unit(by_id["b1"], pattern) == 1
    assert question_unit(by_id["b2"], pattern) == 2
    assert question_unit(by_id["a5"], pattern) is None  # topic t5 is in no unit -> ineligible
    result = assemble(pattern, bank)
    assert "a5" not in result.question_ids


def test_course_outcome_minimum_enforced():
    bank = _bank()
    bank.append(_q("b-co", QuestionType.SHORT_ANSWER, 5, BloomLevel.APPLY, ["t3"], co_ids=["CO2"]))
    pattern = _small_pattern(co_requirements=[{"co_code": "CO2", "min_questions": 1}])
    result = assemble(pattern, bank)
    assert result.satisfied
    assert "b-co" in result.question_ids


def test_evaluate_selection_flags_misfits():
    bank = {q.id: q for q in _bank()}
    picked = [bank[i] for i in ("a0", "a1", "a2", "a3", "b1", "wrong-marks")]
    report = evaluate_selection(_small_pattern(), picked)
    assert not report.compliant
    assert report.unassigned_question_ids == ["wrong-marks"]
    assert report.sections[1].filled == 1


def test_plan_gap_requests_targets_short_sections_and_neglected_topics():
    bank = [q for q in _bank() if q.marks != 5]
    topics = [
        TopicInfo(id="covered", name="Covered", importance=0.5, question_count=9),
        TopicInfo(id="neglected", name="Neglected", importance=0.3, question_count=0),
    ]
    plan = plan_gap_requests(_small_pattern(), bank, topics, max_questions=10)
    assert len(plan) == 2
    assert all(r.section == "Part B" and r.marks == 5 for r in plan)
    assert plan[0].topic_id == "neglected"


def test_plan_gap_requests_is_distribution_aware():
    # Sections are fillable, but Part B's bank questions are all Understand
    # while the pattern needs 5 marks of Analyze: the planner must ask for
    # exactly one Analyze question rather than nothing (or a whole new section).
    bank = [_q(f"a{i}", QuestionType.MCQ, 1, BloomLevel.REMEMBER, [f"t{i}"]) for i in range(4)]
    bank += [_q(f"u{i}", QuestionType.SHORT_ANSWER, 5, BloomLevel.UNDERSTAND, ["t1"]) for i in range(3)]
    pattern = _small_pattern(
        bloom_distribution=[{"bloom_level": 1, "percent": 28.6}, {"bloom_level": 2, "percent": 35.7}, {"bloom_level": 4, "percent": 35.7}],
        tolerance_percent=5,
    )
    assert not assemble(pattern, bank).satisfied
    topics = [TopicInfo(id="t1", name="T1", importance=0.2, question_count=3)]
    plan = plan_gap_requests(pattern, bank, topics, max_questions=10)
    assert [(r.section, int(r.bloom_level), r.marks) for r in plan] == [("Part B", int(BloomLevel.ANALYZE), 5)]


def test_plan_gap_requests_pins_units():
    pattern = _small_pattern(
        units=[{"unit": 1, "topic_ids": ["t0", "t1", "t2", "t3"], "percent": 50}, {"unit": 2, "topic_ids": ["t8"], "percent": 50}],
        tolerance_percent=15,
    )
    topics = [TopicInfo(id=t, name=t.upper(), importance=0.1, question_count=0) for t in ("t0", "t1", "t2", "t3", "t8")]
    plan = plan_gap_requests(pattern, [], topics, max_questions=10)
    assert len(plan) == 6
    unit_marks = {1: 0, 2: 0}
    for r in plan:
        unit_marks[r.unit] += r.marks
        assert (r.unit == 2) == (r.topic_id == "t8")
    # 14 marks split within 50% +/- 15% of 14 -> each unit gets 5..9 marks
    assert all(5 <= m <= 9 for m in unit_marks.values())


# ---------- API ----------


def _pattern_payload(subject_id, **overrides):
    payload = _small_pattern().model_dump(mode="json")
    payload["subject_id"] = subject_id
    payload.update(overrides)
    return payload


def test_pattern_crud_lifecycle(api_client):
    sid = api_client.subject_id
    r = api_client.post("/api/v1/patterns", json=_pattern_payload(sid))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["exam_type"] == "MSE"

    assert [p["id"] for p in api_client.get(f"/api/v1/patterns?subject_id={sid}").json()] == [pid]

    update = _small_pattern(name="Renamed", exam_type="SEE").model_dump(mode="json")
    r = api_client.put(f"/api/v1/patterns/{pid}", json=update)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["exam_type"] == "SEE"

    assert api_client.delete(f"/api/v1/patterns/{pid}").status_code == 200
    assert api_client.get(f"/api/v1/patterns/{pid}").status_code == 404


def test_invalid_pattern_rejected(api_client):
    r = api_client.post("/api/v1/patterns", json=_pattern_payload(api_client.subject_id, total_marks=99))
    assert r.status_code == 422


def test_presets_endpoint(api_client):
    r = api_client.get("/api/v1/patterns/presets")
    assert r.status_code == 200
    assert {p["exam_type"] for p in r.json()} == {"MSE", "SEE"}


def test_assemble_and_check_endpoints_use_subject_bank(api_client):
    from app.core.question_bank import get_question_bank

    get_question_bank(api_client.subject_id).add_many(_bank())
    pid = api_client.post("/api/v1/patterns", json=_pattern_payload(api_client.subject_id)).json()["id"]

    r = api_client.post(f"/api/v1/patterns/{pid}/assemble", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["assembly"]["satisfied"] is True
    assert len(body["assembly"]["question_ids"]) == 6
    assert body["generated"] == []

    r = api_client.post(f"/api/v1/patterns/{pid}/check", json={"question_ids": body["assembly"]["question_ids"]})
    assert r.status_code == 200
    assert r.json()["compliant"] is True


def test_exam_can_be_linked_to_pattern(api_client):
    sid = api_client.subject_id
    pid = api_client.post("/api/v1/patterns", json=_pattern_payload(sid)).json()["id"]
    r = api_client.post("/api/v1/exams", json={"subject_id": sid, "name": "MSE 1", "exam_type": "MSE", "pattern_id": pid})
    assert r.status_code == 200
    assert r.json()["exam_type"] == "MSE"
    assert r.json()["pattern_id"] == pid

    r = api_client.post("/api/v1/exams", json={"subject_id": sid, "name": "Bad", "pattern_id": "nope"})
    assert r.status_code == 404


def test_patterns_are_isolated_between_teachers(api_client):
    pid = api_client.post("/api/v1/patterns", json=_pattern_payload(api_client.subject_id)).json()["id"]
    other = api_client.post(
        "/api/v1/auth/signup", json={"email": "other@test.local", "password": "another-password-1", "name": "Other"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {other}"}
    assert api_client.get(f"/api/v1/patterns/{pid}", headers=headers).status_code == 404
    assert api_client.get(f"/api/v1/patterns?subject_id={api_client.subject_id}", headers=headers).status_code == 404
    assert api_client.delete(f"/api/v1/patterns/{pid}", headers=headers).status_code == 404
