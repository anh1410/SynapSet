from datetime import UTC, datetime, timedelta

from app.schemas.bloom import BloomLevel
from app.schemas.question import CodeTestCase, Question, QuestionType


def _seed_mcq_question(api_client, qid="mcq-1"):
    from app.core.question_bank import get_question_bank

    get_question_bank().add(
        Question(
            id=qid,
            text="2+2?",
            question_type=QuestionType.MCQ,
            marks=2,
            bloom_level=BloomLevel.REMEMBER,
            options=["3", "4"],
            correct_answer="4",
        )
    )
    return qid


def _seed_code_question(api_client, qid="code-1"):
    from app.core.question_bank import get_question_bank

    get_question_bank().add(
        Question(
            id=qid,
            text="Fix the doubler",
            question_type=QuestionType.CODE_FIX,
            marks=4,
            bloom_level=BloomLevel.APPLY,
            code_language="python",
            starter_code="n = int(input())\nprint(n + 1)",
            correct_answer="n = int(input())\nprint(n * 2)",
            test_cases=[CodeTestCase(input="5\n", expected_output="10")],
        )
    )
    return qid


def _create_live_exam(api_client, question_ids, password=""):
    r = api_client.post(
        "/api/v1/exams",
        json={"name": "Quiz", "question_ids": question_ids, "total_marks": sum(1 for _ in question_ids) * 2},
    )
    exam_id = r.json()["id"]
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    update = {"go_live_at": past}
    if password:
        update["password"] = password
    api_client.patch(f"/api/v1/exams/{exam_id}", json=update)
    return exam_id


def test_verify_password_correct(api_client):
    qid = _seed_mcq_question(api_client)
    exam_id = _create_live_exam(api_client, [qid], password="letmein")

    r = api_client.post(f"/api/v1/exams/{exam_id}/verify-password", json={"password": "letmein"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == exam_id
    assert len(body["questions"]) == 1
    # No answer key leaked to the student.
    assert "correct_answer" not in body["questions"][0]


def test_verify_password_wrong_rejected(api_client):
    qid = _seed_mcq_question(api_client)
    exam_id = _create_live_exam(api_client, [qid], password="letmein")

    r = api_client.post(f"/api/v1/exams/{exam_id}/verify-password", json={"password": "nope"})
    assert r.status_code == 401


def test_verify_password_not_live_yet_rejected(api_client):
    qid = _seed_mcq_question(api_client)
    r = api_client.post("/api/v1/exams", json={"name": "Future Quiz", "question_ids": [qid]})
    exam_id = r.json()["id"]
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    api_client.patch(f"/api/v1/exams/{exam_id}", json={"go_live_at": future})

    r = api_client.post(f"/api/v1/exams/{exam_id}/verify-password", json={"password": ""})
    assert r.status_code == 403


def test_submit_grades_immediately_and_scores(api_client):
    mcq_id = _seed_mcq_question(api_client)
    code_id = _seed_code_question(api_client)
    exam_id = _create_live_exam(api_client, [mcq_id, code_id])

    r = api_client.post(
        f"/api/v1/exams/{exam_id}/submit",
        json={
            "student_name": "Alice",
            "answers": [
                {"question_id": mcq_id, "answer": "4"},
                {"question_id": code_id, "answer": "n = int(input())\nprint(n * 2)"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_marks_awarded"] == 6
    assert body["total_max_marks"] == 6
    assert body["fully_auto_graded"] is True

    # And it shows up for the teacher.
    r = api_client.get(f"/api/v1/exams/{exam_id}/submissions")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["student_name"] == "Alice"


def test_submit_wrong_answers_scores_zero(api_client):
    mcq_id = _seed_mcq_question(api_client)
    exam_id = _create_live_exam(api_client, [mcq_id])

    r = api_client.post(
        f"/api/v1/exams/{exam_id}/submit",
        json={"student_name": "Bob", "answers": [{"question_id": mcq_id, "answer": "3"}]},
    )
    assert r.status_code == 200
    assert r.json()["total_marks_awarded"] == 0


def test_submit_wrong_password_rejected(api_client):
    qid = _seed_mcq_question(api_client)
    exam_id = _create_live_exam(api_client, [qid], password="secret")

    r = api_client.post(
        f"/api/v1/exams/{exam_id}/submit",
        json={"student_name": "Eve", "password": "wrong", "answers": []},
    )
    assert r.status_code == 401


def test_submit_after_closed_rejected(api_client):
    qid = _seed_mcq_question(api_client)
    exam_id = _create_live_exam(api_client, [qid])
    api_client.patch(f"/api/v1/exams/{exam_id}", json={"status": "closed"})

    r = api_client.post(
        f"/api/v1/exams/{exam_id}/submit",
        json={"student_name": "Alice", "answers": [{"question_id": qid, "answer": "4"}]},
    )
    assert r.status_code == 403


def test_submissions_not_visible_to_other_teacher(api_client):
    qid = _seed_mcq_question(api_client)
    exam_id = _create_live_exam(api_client, [qid])
    api_client.post(
        f"/api/v1/exams/{exam_id}/submit",
        json={"student_name": "Alice", "answers": [{"question_id": qid, "answer": "4"}]},
    )

    signup = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "other2@test.local", "password": "test-password-123", "name": "Other Teacher"},
    )
    other_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    r = api_client.get(f"/api/v1/exams/{exam_id}/submissions", headers=other_headers)
    assert r.status_code == 404
