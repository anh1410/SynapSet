from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_questions_list_empty_bank(api_client):
    r = api_client.get("/api/v1/questions")
    assert r.status_code == 200
    assert r.json() == []


def test_graph_summary_empty(api_client):
    r = api_client.get("/api/v1/graph/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] == 0
    assert body["edges"] == 0


def test_check_duplicates_against_seeded_bank(api_client):
    from app.core.question_bank import get_question_bank

    bank = get_question_bank()
    bank.add(
        Question(
            id="seed-1",
            text="Define virtualization and its role in cloud computing.",
            question_type=QuestionType.SHORT_ANSWER,
            marks=5,
            bloom_level=BloomLevel.UNDERSTAND,
            topic_ids=["virtualization"],
        )
    )

    candidate = {
        "id": "cand-1",
        "text": "Describe virtualization and what role it plays in cloud computing.",
        "question_type": "short_answer",
        "marks": 5,
        "bloom_level": 2,
        "topic_ids": ["virtualization"],
    }
    r = api_client.post("/api/v1/questions/check-duplicates", json={"question": candidate, "threshold": 0.5})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["is_duplicate"] is True


def test_paper_optimize_seeded_bank(api_client):
    from app.core.question_bank import get_question_bank

    bank = get_question_bank()
    bank.add_many(
        [
            Question(id="a", text="qa", question_type=QuestionType.MCQ, marks=1, bloom_level=BloomLevel.REMEMBER),
            Question(id="b", text="qb", question_type=QuestionType.SHORT_ANSWER, marks=5, bloom_level=BloomLevel.UNDERSTAND),
        ]
    )

    payload = {"constraints": {"total_marks": 6, "bloom_distribution": {"weights": {"1": 0.2, "2": 0.8}}}}
    r = api_client.post("/api/v1/paper/optimize", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OPTIMAL"
    assert sum(q["marks"] for q in body["selected"]) == 6


def test_paper_optimize_no_candidates(api_client):
    payload = {"constraints": {"total_marks": 5, "bloom_distribution": {"weights": {"1": 1.0}}}}
    r = api_client.post("/api/v1/paper/optimize", json=payload)
    assert r.status_code == 400


def test_paper_export_pdf(api_client):
    payload = {
        "title": "Test Paper",
        "questions": [
            {"id": "1", "text": "Sample question?", "question_type": "short_answer", "marks": 5, "bloom_level": 2, "topic_ids": []}
        ],
        "format": "pdf",
    }
    r = api_client.post("/api/v1/paper/export", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_paper_export_docx(api_client):
    payload = {
        "title": "Test Paper",
        "questions": [
            {
                "id": "1",
                "text": "Sample question?",
                "question_type": "mcq",
                "marks": 1,
                "bloom_level": 1,
                "topic_ids": [],
                "options": ["a", "b", "c", "d"],
                "correct_answer": "a",
            }
        ],
        "format": "docx",
    }
    r = api_client.post("/api/v1/paper/export", json=payload)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


def test_paper_export_invalid_format(api_client):
    r = api_client.post("/api/v1/paper/export", json={"title": "t", "questions": [], "format": "xyz"})
    assert r.status_code == 400
