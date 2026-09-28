"""Small builders shared by the API tests (questions, exams, patterns)."""

from datetime import datetime

from app.schemas.bloom import BloomLevel
from app.schemas.question import CodeTestCase, Question, QuestionProvenance, QuestionType, SourceChunk


def q(qid, qtype=QuestionType.SHORT_ANSWER, marks=5, bloom=BloomLevel.UNDERSTAND, topics=("stacks",),
      difficulty=5.0, co_ids=(), **extra) -> Question:
    fields = dict(
        id=qid, text=f"Question {qid}?", question_type=qtype, marks=marks, bloom_level=bloom,
        topic_ids=list(topics), co_ids=list(co_ids), difficulty_score=difficulty,
    )
    if qtype in (QuestionType.MCQ, QuestionType.FILL_IN_BLANK):
        fields.update(options=["right", "wrong", "other", "none"], correct_answer="right")
    if qtype == QuestionType.CODE_FIX:
        fields.update(code_language="python", starter_code="print(int(input()) + 1)",
                      correct_answer="print(int(input()) * 2)",
                      test_cases=[CodeTestCase(input="2\n", expected_output="4"), CodeTestCase(input="3\n", expected_output="6")])
    fields.update(extra)
    return Question(**fields)


def provenance(topic="Stacks") -> QuestionProvenance:
    return QuestionProvenance(
        requested_topic=topic,
        retrieved_chunks=[SourceChunk(source_document="notes.pdf", chunk_index=3, excerpt="Stacks are LIFO...", relevance=0.91)],
        graph_relations=["Stacks --[PREREQUISITE_OF]--> Recursion"],
        model="test-model",
    )


def seed(api_client, questions: list[Question]) -> None:
    from app.core.question_bank import get_question_bank

    get_question_bank(api_client.subject_id).add_many(questions)


def seed_graph(api_client, topics: dict[str, str], prereqs=()) -> None:
    from app.core.graph_store import get_graph_store

    gs = get_graph_store(api_client.subject_id)
    for tid, name in topics.items():
        gs.add_topic(tid, name=name, description=f"About {name}")
    for a, b in prereqs:
        gs.add_relation(a, b, "PREREQUISITE_OF")
    gs.save()


def make_exam(api_client, question_ids, *, name="Paper", pattern_id=None, exam_type="QUIZ",
              go_live: datetime | None = None, duration=None, closes: datetime | None = None) -> str:
    from app.core.question_bank import get_question_bank

    bank = get_question_bank(api_client.subject_id)
    body = {
        "subject_id": api_client.subject_id, "name": name, "question_ids": list(question_ids),
        "total_marks": sum(bank.get(i).marks for i in question_ids), "exam_type": exam_type,
        "duration_minutes": duration,
    }
    if pattern_id:
        body["pattern_id"] = pattern_id
    r = api_client.post("/api/v1/exams", json=body)
    assert r.status_code == 200, r.text
    exam_id = r.json()["id"]
    update = {}
    if go_live is not None:
        update["go_live_at"] = go_live.isoformat()
    if closes is not None:
        update["closes_at"] = closes.isoformat()
    if update:
        assert api_client.patch(f"/api/v1/exams/{exam_id}", json=update).status_code == 200
    return exam_id


def small_pattern(api_client, **overrides) -> str:
    body = {
        "subject_id": api_client.subject_id, "name": "Mini MSE", "exam_type": "MSE", "total_marks": 14,
        "duration_minutes": 60, "tolerance_percent": 10,
        "sections": [
            {"name": "Part A", "num_questions": 4, "marks_per_question": 1, "question_types": ["mcq"], "bloom_levels": []},
            {"name": "Part B", "num_questions": 2, "marks_per_question": 5, "question_types": [], "bloom_levels": []},
        ],
    }
    body.update(overrides)
    r = api_client.post("/api/v1/patterns", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def other_teacher_headers(api_client) -> dict:
    token = api_client.post(
        "/api/v1/auth/signup", json={"email": "intruder@test.local", "password": "intruder-password-1", "name": "Intruder"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def submit(api_client, exam_id, name, ident, answers: dict[str, str]):
    r = api_client.post(f"/api/v1/exams/{exam_id}/submit", json={
        "student_name": name, "student_identifier": ident,
        "answers": [{"question_id": k, "answer": v} for k, v in answers.items()],
    })
    assert r.status_code == 200, r.text
    return r.json()
