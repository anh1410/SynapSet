from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_questions_list_empty_bank(api_client):
    r = api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_graph_empty(api_client):
    r = api_client.get(f"/api/v1/graph?subject_id={api_client.subject_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] == []
    assert body["edges"] == []


def test_documents_empty(api_client):
    r = api_client.get(f"/api/v1/graph/documents?subject_id={api_client.subject_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_exams_empty(api_client):
    r = api_client.get(f"/api/v1/exams?subject_id={api_client.subject_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_exam_lifecycle(api_client):
    from app.core.question_bank import get_question_bank

    bank = get_question_bank(api_client.subject_id)
    bank.add(
        Question(id="q1", text="qa", question_type=QuestionType.MCQ, marks=1, bloom_level=BloomLevel.REMEMBER)
    )

    r = api_client.post(
        "/api/v1/exams",
        json={
            "subject_id": api_client.subject_id,
            "name": "Weekly Quiz 1",
            "total_marks": 1,
            "duration_minutes": 30,
            "question_ids": ["q1"],
        },
    )
    assert r.status_code == 200
    exam_id = r.json()["id"]
    assert r.json()["status"] == "draft"
    assert r.json()["bucket"] == "draft"

    r = api_client.get(f"/api/v1/exams/{exam_id}")
    assert r.status_code == 200
    assert len(r.json()["questions"]) == 1

    r = api_client.patch(
        f"/api/v1/exams/{exam_id}",
        json={"go_live_at": "2999-01-01T00:00:00Z", "password": "sesame"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"
    assert r.json()["bucket"] == "upcoming"

    r = api_client.get(f"/api/v1/exams?subject_id={api_client.subject_id}")
    assert len(r.json()) == 1
    assert r.json()[0]["password"] == "sesame"

    r = api_client.delete(f"/api/v1/exams/{exam_id}")
    assert r.status_code == 200
    assert api_client.get(f"/api/v1/exams/{exam_id}").status_code == 404


def test_exam_not_owned_by_another_teacher_is_404(api_client):
    r = api_client.post("/api/v1/exams", json={"subject_id": api_client.subject_id, "name": "Mine"})
    exam_id = r.json()["id"]

    signup = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "other@test.local", "password": "test-password-123", "name": "Other Teacher"},
    )
    other_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    r = api_client.get(f"/api/v1/exams/{exam_id}", headers=other_headers)
    assert r.status_code == 404


def test_subject_not_owned_by_another_teacher_is_404(api_client):
    signup = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "other2@test.local", "password": "test-password-123", "name": "Other Teacher"},
    )
    other_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    r = api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}", headers=other_headers)
    assert r.status_code == 404


def test_check_duplicates_against_seeded_bank(api_client):
    from app.core.question_bank import get_question_bank

    bank = get_question_bank(api_client.subject_id)
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
    r = api_client.post(
        "/api/v1/questions/check-duplicates",
        json={"subject_id": api_client.subject_id, "question": candidate, "threshold": 0.5},
    )
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["is_duplicate"] is True


def test_save_and_delete_question(api_client):
    question = {
        "id": "manual-1",
        "text": "What is a hypervisor?",
        "question_type": "short_answer",
        "marks": 5,
        "bloom_level": 2,
        "topic_ids": [],
    }
    r = api_client.post(f"/api/v1/questions?subject_id={api_client.subject_id}", json=question)
    assert r.status_code == 200
    assert r.json()["id"] == "manual-1"

    r = api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}")
    assert len(r.json()) == 1

    r = api_client.delete(f"/api/v1/questions/manual-1?subject_id={api_client.subject_id}")
    assert r.status_code == 200

    r = api_client.delete(f"/api/v1/questions/manual-1?subject_id={api_client.subject_id}")
    assert r.status_code == 404


def test_delete_document_not_found(api_client):
    r = api_client.delete(f"/api/v1/graph/documents/does-not-exist?subject_id={api_client.subject_id}")
    assert r.status_code == 404


def test_grade_endpoint_mcq(api_client):
    from app.core.question_bank import get_question_bank

    get_question_bank(api_client.subject_id).add(
        Question(
            id="mcq-1",
            text="2+2?",
            question_type=QuestionType.MCQ,
            marks=1,
            bloom_level=BloomLevel.REMEMBER,
            options=["3", "4"],
            correct_answer="4",
        )
    )
    r = api_client.post("/api/v1/questions/mcq-1/grade", json={"subject_id": api_client.subject_id, "answer": "4"})
    assert r.status_code == 200
    assert r.json()["correct"] is True
    assert r.json()["marks_awarded"] == 1


def test_grade_endpoint_short_answer_rejected(api_client):
    from app.core.question_bank import get_question_bank

    get_question_bank(api_client.subject_id).add(
        Question(id="sa-1", text="Explain X.", question_type=QuestionType.SHORT_ANSWER, marks=5, bloom_level=BloomLevel.UNDERSTAND)
    )
    r = api_client.post(
        "/api/v1/questions/sa-1/grade", json={"subject_id": api_client.subject_id, "answer": "some text"}
    )
    assert r.status_code == 400


def test_grade_endpoint_question_not_found(api_client):
    r = api_client.post(
        "/api/v1/questions/does-not-exist/grade", json={"subject_id": api_client.subject_id, "answer": "x"}
    )
    assert r.status_code == 404
