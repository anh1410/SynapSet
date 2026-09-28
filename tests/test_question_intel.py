"""Question-bank intelligence (usage history, avoid-recent assembly) and
Graph-RAG evidence (recorded provenance vs reconstructed retrieval)."""

from datetime import timedelta
from types import SimpleNamespace

from app.schemas.bloom import BloomLevel
from app.schemas.generation import GeneratedQuestionDraft, QuestionDraftBatch
from app.schemas.question import QuestionType
from tests.conftest import T0
from tests.factories import make_exam, other_teacher_headers, provenance, q, seed, seed_graph, small_pattern, submit

MCQ, SA = QuestionType.MCQ, QuestionType.SHORT_ANSWER


def _usage(api_client):
    r = api_client.get(f"/api/v1/questions/usage?subject_id={api_client.subject_id}")
    assert r.status_code == 200, r.text
    return r.json()


# ---------- usage statistics ----------


def test_usage_counts_published_exams_and_responses(api_client, clock):
    seed(api_client, [q("u1", MCQ, 2), q("u2", MCQ, 2), q("u3", MCQ, 2)])
    e1 = make_exam(api_client, ["u1", "u2"], name="Quiz 1", go_live=T0 - timedelta(days=40))
    make_exam(api_client, ["u1"], name="Quiz 2", go_live=T0 - timedelta(days=3))
    make_exam(api_client, ["u2"], name="Draft only")  # drafts don't count as use
    clock.advance(minutes=1)
    body = _usage(api_client)
    assert body["thresholds"] == {"recent_days": 30, "frequent_count": 3}
    u = body["usage"]
    assert u["u1"]["times_used"] == 2 and u["u1"]["recently_used"] is True
    assert [x["name"] for x in u["u1"]["exams"]] == ["Quiz 2", "Quiz 1"]
    assert u["u2"]["times_used"] == 1 and u["u2"]["recently_used"] is False
    assert {x["bucket"] for x in u["u2"]["exams"]} == {"live", "draft"}
    assert u["u3"]["never_used"] is True and u["u3"]["last_used_at"] is None

    # Quiz 1 has no duration, so the untimed legacy submit works; responses feed average_percent.
    submit(api_client, e1, "A", "R1", {"u1": "right", "u2": "wrong"})
    submit(api_client, e1, "B", "R2", {"u1": "right", "u2": "right"})
    u = _usage(api_client)["usage"]
    assert u["u1"]["responses"] == 2 and u["u1"]["average_percent"] == 100.0
    assert u["u2"]["average_percent"] == 50.0


def test_frequently_used_threshold(api_client, clock):
    seed(api_client, [q("f1", MCQ, 1)])
    for i in range(3):
        make_exam(api_client, ["f1"], name=f"E{i}", go_live=T0 - timedelta(days=i + 1))
    assert _usage(api_client)["usage"]["f1"]["frequently_used"] is True


def test_assembler_can_avoid_recently_used_questions(api_client, clock):
    seed(api_client, [
        *(q(f"a{i}", MCQ, 1, BloomLevel.REMEMBER, ["stacks"]) for i in range(8)),
        *(q(f"b{i}", SA, 5, BloomLevel.APPLY, ["stacks"]) for i in range(4)),
    ])
    pid = small_pattern(api_client)
    make_exam(api_client, ["a0", "a1", "a2", "a3", "b0", "b1"], pattern_id=pid, go_live=T0 - timedelta(days=2))
    r = api_client.post(f"/api/v1/patterns/{pid}/assemble", json={"avoid_recent_days": 30})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["excluded_recent"] == 6
    assert body["assembly"]["satisfied"] is True
    assert not {"a0", "a1", "a2", "a3", "b0", "b1"} & set(body["assembly"]["question_ids"])
    # Without the option, recent questions are still eligible.
    assert api_client.post(f"/api/v1/patterns/{pid}/assemble", json={}).json()["excluded_recent"] == 0


def test_gap_filling_never_generates_for_course_outcome_nodes(api_client, clock, monkeypatch):
    from app.core.graph_store import get_graph_store

    seed_graph(api_client, {"stacks": "Stacks", "co2": "CO2"})
    gs = get_graph_store(api_client.subject_id)
    gs.add_relation("stacks", "co2", "MAPS_TO")
    gs.save()
    asked = []
    monkeypatch.setattr("app.api.patterns.generate_questions", lambda **kw: asked.append(kw["topic"]) or [])
    pid = small_pattern(api_client)
    api_client.post(f"/api/v1/patterns/{pid}/assemble", json={"generate_missing": True})
    assert asked and set(asked) == {"Stacks"}


# ---------- evidence ----------


def test_evidence_returns_recorded_provenance(api_client, clock):
    seed_graph(api_client, {"stacks": "Stacks", "recursion": "Recursion", "arrays": "Arrays"},
               prereqs=[("arrays", "stacks"), ("stacks", "recursion")])
    seed(api_client, [q("e1", SA, 5, BloomLevel.APPLY, ["stacks"], provenance=provenance("Stacks"), co_ids=["CO1"])])
    r = api_client.get(f"/api/v1/questions/e1/evidence?subject_id={api_client.subject_id}")
    assert r.status_code == 200, r.text
    ev = r.json()
    assert ev["recorded"] is True and ev["requested_topic"] == "Stacks"
    assert ev["chunks"][0]["source_document"] == "notes.pdf" and ev["chunks"][0]["relevance"] == 0.91
    assert ev["graph_relations"] == ["Stacks --[PREREQUISITE_OF]--> Recursion"]
    topic = ev["topics"][0]
    assert topic["name"] == "Stacks" and topic["prerequisites"] == ["Arrays"] and topic["leads_to"] == ["Recursion"]
    assert ev["bloom_level"] == 3 and ev["difficulty"] == "medium" and ev["skill_category"] == "reasoning"


def test_evidence_reconstructed_for_questions_without_provenance(api_client, clock, monkeypatch):
    seed(api_client, [q("old", SA, 5)])
    monkeypatch.setattr(
        "app.services.evidence.query_similar_chunks",
        lambda text, subject_id, n_results: [{"text": "Closest passage", "metadata": {"source_document": "unit1.pdf", "chunk_index": 0}, "distance": 0.2}],
    )
    ev = api_client.get(f"/api/v1/questions/old/evidence?subject_id={api_client.subject_id}").json()
    assert ev["recorded"] is False
    assert "weren't recorded" in ev["note"]
    assert ev["chunks"][0]["source_document"] == "unit1.pdf" and ev["chunks"][0]["relevance"] == 0.8


def test_evidence_degrades_gracefully_when_retrieval_fails(api_client, clock, monkeypatch):
    seed(api_client, [q("old", SA, 5)])

    def fail(*a, **k):
        raise RuntimeError("no embeddings available")

    monkeypatch.setattr("app.services.evidence.query_similar_chunks", fail)
    ev = api_client.get(f"/api/v1/questions/old/evidence?subject_id={api_client.subject_id}").json()
    assert ev["recorded"] is False and ev["chunks"] == [] and "couldn't be retrieved" in ev["note"]


def test_generation_records_provenance(api_client, clock, monkeypatch):
    """The real generation path stores what it retrieved (Gemini and the vector store mocked)."""
    from app.core.graph_store import get_graph_store
    from app.services import question_generation as gen

    seed_graph(api_client, {"stacks": "Stacks", "recursion": "Recursion"}, prereqs=[("stacks", "recursion")])
    hits = [{"text": "A stack is a LIFO structure. " * 5, "metadata": {"source_document": "ds_notes.pdf", "chunk_index": 2}, "distance": 0.1}]
    monkeypatch.setattr(gen, "query_similar_chunks", lambda *a, **k: hits)
    draft = GeneratedQuestionDraft(text="Explain LIFO.", question_type=SA, bloom_level="UNDERSTAND", marks=5,
                                   correct_answer="Last in, first out", topic_names=["Stacks"])
    fake_client = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **kw: SimpleNamespace(parsed=QuestionDraftBatch(questions=[draft]))))
    monkeypatch.setattr(gen, "get_genai_client", lambda: fake_client)

    [question] = gen.generate_questions("Stacks", get_graph_store(api_client.subject_id), api_client.subject_id, num_questions=1)
    p = question.provenance
    assert p.requested_topic == "Stacks"
    assert p.retrieved_chunks[0].source_document == "ds_notes.pdf" and p.retrieved_chunks[0].relevance == 0.9
    assert p.graph_relations == ["Stacks --[PREREQUISITE_OF]--> Recursion"]
    assert question.source_document == "ds_notes.pdf"


def test_usage_and_evidence_isolated_between_teachers(api_client, clock):
    seed(api_client, [q("s1", MCQ, 1, provenance=provenance())])
    h = other_teacher_headers(api_client)
    sid = api_client.subject_id
    assert api_client.get(f"/api/v1/questions/usage?subject_id={sid}", headers=h).status_code == 404
    assert api_client.get(f"/api/v1/questions/s1/evidence?subject_id={sid}", headers=h).status_code == 404
