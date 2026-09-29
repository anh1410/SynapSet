"""Student dashboard: accounts, role separation, join codes, enrolment,
exam list with the student's own status, dashboard-linked attempts, and
results (final score only once fully graded; no answer key / correctness)."""

import json
from datetime import timedelta

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from tests.conftest import T0
from tests.factories import make_exam, other_teacher_headers, q, seed

MCQ, LONG = QuestionType.MCQ, QuestionType.LONG_ANSWER

# Things a student must never see on the dashboard.
FORBIDDEN = {"password", "correct_answer", "test_cases", "questions", "answers", "correct", "detail",
             "difficulty_score", "topic_ids", "bloom_level", "feedback", "password_hash", "question_ids"}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _signup(api_client, name="Asha Rao", roll="CS-101", email="asha@student.test", password="student-pass-1"):
    return api_client.post("/api/v1/student/auth/signup", json={
        "name": name, "roll_number": roll, "email": email, "password": password}, headers={"Authorization": ""})


def _student(api_client, **kwargs) -> dict:
    r = _signup(api_client, **kwargs)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _join_code(api_client, subject_id=None) -> str:
    r = api_client.get(f"/api/v1/subjects/{subject_id or api_client.subject_id}/join-code")
    assert r.status_code == 200, r.text
    return r.json()["join_code"]


def _join(api_client, headers, code):
    return api_client.post("/api/v1/student/subjects/join", json={"code": code}, headers=headers)


def _exams(api_client, headers) -> list[dict]:
    r = api_client.get("/api/v1/student/exams", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["exams"]


def _start(api_client, exam_id, headers=None, name="Someone", roll=None, password=""):
    return api_client.post(f"/api/v1/exams/{exam_id}/start", headers=headers or {"Authorization": ""},
                           json={"student_name": name, "student_identifier": roll, "password": password})


def _submit(api_client, exam_id, attempt_id, answers, name="Asha Rao", password=""):
    return api_client.post(f"/api/v1/exams/{exam_id}/submit", headers={"Authorization": ""}, json={
        "student_name": name, "attempt_id": attempt_id, "password": password,
        "answers": [{"question_id": k, "answer": v} for k, v in answers.items()]})


# ---------- accounts & roles ----------


def test_signup_login_me(api_client):
    r = _signup(api_client)
    assert r.status_code == 200
    assert r.json()["student"]["roll_number"] == "CS-101"
    assert "password_hash" not in r.json()["student"]
    login = api_client.post("/api/v1/student/auth/login", headers={"Authorization": ""},
                            json={"email": "ASHA@student.test", "password": "student-pass-1"})
    assert login.status_code == 200
    me = api_client.get("/api/v1/student/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["name"] == "Asha Rao"


def test_signup_validation_and_duplicates(api_client):
    assert _signup(api_client, password="short").status_code == 422
    assert _signup(api_client, roll="  ").status_code == 422
    assert _signup(api_client).status_code == 200
    assert _signup(api_client, roll="CS-999").status_code == 409  # same email
    # Same roll number (normalised) = same exam identity: only one account.
    assert _signup(api_client, email="other@student.test", roll=" cs-101 ").status_code == 409


def test_bad_login(api_client):
    _signup(api_client)
    r = api_client.post("/api/v1/student/auth/login", headers={"Authorization": ""},
                        json={"email": "asha@student.test", "password": "wrong-password"})
    assert r.status_code == 401


def test_student_and_teacher_tokens_are_not_interchangeable(api_client):
    student = _student(api_client)
    # Student token on teacher endpoints.
    assert api_client.get("/api/v1/subjects", headers=student).status_code == 401
    assert api_client.get("/api/v1/auth/me", headers=student).status_code == 401
    assert api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}", headers=student).status_code == 401
    # Teacher token (the client's default header) on student endpoints.
    assert api_client.get("/api/v1/student/exams").status_code == 401
    assert api_client.get("/api/v1/student/auth/me").status_code == 401
    # No token at all.
    assert api_client.get("/api/v1/student/results", headers={"Authorization": ""}).status_code in (401, 403)


# ---------- join codes & enrolment ----------


def test_join_code_generated_rotated_and_teacher_scoped(api_client):
    code = _join_code(api_client)
    assert len(code) == 7 and code == _join_code(api_client)  # stable until rotated
    rotated = api_client.post(f"/api/v1/subjects/{api_client.subject_id}/join-code/rotate").json()["join_code"]
    assert rotated != code
    other = other_teacher_headers(api_client)
    assert api_client.get(f"/api/v1/subjects/{api_client.subject_id}/join-code", headers=other).status_code == 404
    assert api_client.post(f"/api/v1/subjects/{api_client.subject_id}/join-code/rotate", headers=other).status_code == 404
    assert api_client.get(f"/api/v1/subjects/{api_client.subject_id}/students", headers=other).status_code == 404


def test_new_subjects_get_a_join_code(api_client):
    s = api_client.post("/api/v1/subjects", json={"name": "Another"}).json()
    assert s["join_code"] and len(s["join_code"]) == 7


def test_join_leave_and_teacher_sees_enrolment(api_client):
    student = _student(api_client)
    code = _join_code(api_client)
    assert _join(api_client, student, "nope123").status_code == 404
    r = _join(api_client, student, f" {code.lower()} ")  # case/whitespace tolerant
    assert r.status_code == 200 and r.json()["name"] == "Test Subject" and r.json()["teacher_name"] == "Test Teacher"
    assert _join(api_client, student, code).status_code == 200  # idempotent
    subjects = api_client.get("/api/v1/student/subjects", headers=student).json()
    assert [s["id"] for s in subjects] == [api_client.subject_id]

    enrolled = api_client.get(f"/api/v1/subjects/{api_client.subject_id}/students").json()
    assert [(s["name"], s["roll_number"]) for s in enrolled] == [("Asha Rao", "CS-101")]
    assert api_client.get(f"/api/v1/subjects/{api_client.subject_id}/join-code").json()["enrolled_count"] == 1

    # Rotating the code keeps existing enrolments but the old code stops working.
    api_client.post(f"/api/v1/subjects/{api_client.subject_id}/join-code/rotate")
    other = _student(api_client, name="Ben", roll="CS-102", email="ben@student.test")
    assert _join(api_client, other, code).status_code == 404
    assert len(api_client.get("/api/v1/student/subjects", headers=student).json()) == 1

    assert api_client.delete(f"/api/v1/student/subjects/{api_client.subject_id}", headers=student).status_code == 200
    assert api_client.get("/api/v1/student/subjects", headers=student).json() == []
    assert api_client.delete(f"/api/v1/student/subjects/{api_client.subject_id}", headers=student).status_code == 404


# ---------- exams ----------


def test_exams_only_from_joined_subjects_and_never_drafts(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    live = make_exam(api_client, ["m1"], name="Live", go_live=T0 - timedelta(minutes=1), duration=30)
    upcoming = make_exam(api_client, ["m1"], name="Soon", go_live=T0 + timedelta(hours=1))
    make_exam(api_client, ["m1"], name="Draft")
    student = _student(api_client)
    assert _exams(api_client, student) == []  # not joined yet

    _join(api_client, student, _join_code(api_client))
    rows = {e["name"]: e for e in _exams(api_client, student)}
    assert set(rows) == {"Live", "Soon"}
    assert rows["Live"]["id"] == live and rows["Live"]["state"] == "live" and rows["Live"]["my_status"] == "not_started"
    assert rows["Soon"]["id"] == upcoming and rows["Soon"]["state"] == "upcoming"
    assert rows["Soon"]["opens_in_seconds"] == 3600
    assert rows["Live"]["subject_name"] == "Test Subject" and rows["Live"]["question_count"] == 1


def test_exam_rows_hide_password_and_questions(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1))
    api_client.patch(f"/api/v1/exams/{exam_id}", json={"password": "s3cret-pw"})
    student = _student(api_client)
    _join(api_client, student, _join_code(api_client))
    body = api_client.get("/api/v1/student/exams", headers=student).json()
    assert body["exams"][0]["password_required"] is True
    assert _keys(body) & FORBIDDEN == set()
    assert "s3cret-pw" not in json.dumps(body) and "right" not in json.dumps(body)


def test_other_teachers_subjects_are_not_visible(api_client, clock):
    other = other_teacher_headers(api_client)
    other_subject = api_client.post("/api/v1/subjects", json={"name": "Theirs"}, headers=other).json()
    seed(api_client, [q("m1", MCQ, 2)])
    make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1))  # in the default subject
    student = _student(api_client)
    _join(api_client, student, other_subject["join_code"])
    assert _exams(api_client, student) == []  # joined "Theirs" only; no exams there
    assert [s["name"] for s in api_client.get("/api/v1/student/subjects", headers=student).json()] == ["Theirs"]


def test_my_status_through_the_attempt_lifecycle(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1), duration=30)
    missed = make_exam(api_client, ["m1"], name="Missed", go_live=T0 - timedelta(hours=2),
                       closes=T0 - timedelta(hours=1))
    student = _student(api_client)
    _join(api_client, student, _join_code(api_client))
    status = lambda: {e["id"]: e for e in _exams(api_client, student)}  # noqa: E731
    assert status()[missed]["my_status"] == "missed"

    aid = _start(api_client, exam_id, headers=student).json()["attempt"]["attempt_id"]
    clock.advance(minutes=10)
    row = status()[exam_id]
    assert row["my_status"] == "in_progress" and row["remaining_seconds"] == 20 * 60

    assert _submit(api_client, exam_id, aid, {"m1": "right"}).status_code == 200
    row = status()[exam_id]
    assert row["my_status"] == "submitted" and row["submitted_at"].startswith("2026-10-01T09:10")


def test_status_auto_submitted_and_not_submitted(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    saved = make_exam(api_client, ["m1"], name="Saved", go_live=T0 - timedelta(minutes=1), duration=5)
    empty = make_exam(api_client, ["m1"], name="Empty", go_live=T0 - timedelta(minutes=1), duration=5)
    student = _student(api_client)
    _join(api_client, student, _join_code(api_client))
    aid = _start(api_client, saved, headers=student).json()["attempt"]["attempt_id"]
    api_client.put(f"/api/v1/exams/{saved}/attempts/{aid}/answers", headers={"Authorization": ""},
                   json={"answers": [{"question_id": "m1", "answer": "right"}], "seq": 1})
    _start(api_client, empty, headers=student)
    clock.advance(minutes=10)
    rows = {e["name"]: e["my_status"] for e in _exams(api_client, student)}
    assert rows == {"Saved": "auto_submitted", "Empty": "not_submitted"}


# ---------- dashboard-linked attempts ----------


def test_start_with_student_token_uses_account_identity_and_links_attempt(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1), duration=30)
    student = _student(api_client)
    # Whatever name/roll the request claims, the account's identity is used.
    r = _start(api_client, exam_id, headers=student, name="Impostor", roll="X-1")
    assert r.status_code == 200
    attempts = api_client.get(f"/api/v1/exams/{exam_id}/attempts").json()
    assert [(a["student_name"], a["student_identifier"]) for a in attempts] == [("Asha Rao", "CS-101")]
    # The same attempt resumes anonymously via the link too (same roll number).
    again = _start(api_client, exam_id, name="Asha Rao", roll="cs-101")
    assert again.json()["attempt"]["attempt_id"] == r.json()["attempt"]["attempt_id"]


def test_invalid_student_token_on_start_is_rejected(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1))
    assert _start(api_client, exam_id, headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_teacher_token_on_start_is_treated_as_anonymous(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1))
    teacher_auth = {"Authorization": api_client.headers["Authorization"]}
    r = _start(api_client, exam_id, headers=teacher_auth, name="Walk-in", roll="W-1")
    assert r.status_code == 200
    [attempt] = api_client.get(f"/api/v1/exams/{exam_id}/attempts").json()
    assert attempt["student_name"] == "Walk-in"  # request identity used, nothing linked


def test_link_attempt_is_claimed_when_resumed_from_dashboard(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1), duration=30)
    link = _start(api_client, exam_id, name="Asha Rao", roll="CS-101").json()["attempt"]["attempt_id"]
    student = _student(api_client)
    resumed = _start(api_client, exam_id, headers=student).json()["attempt"]["attempt_id"]
    assert resumed == link
    _submit(api_client, exam_id, link, {"m1": "right"})
    assert [r["exam_id"] for r in api_client.get("/api/v1/student/results", headers=student).json()] == [exam_id]


# ---------- results ----------


def test_results_pending_then_final_after_teacher_grading(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER), q("l1", LONG, 8, BloomLevel.EVALUATE)])
    exam_id = make_exam(api_client, ["m1", "l1"], name="Mid-term", exam_type="MSE",
                        go_live=T0 - timedelta(minutes=1), duration=30)
    student = _student(api_client)
    _join(api_client, student, _join_code(api_client))
    aid = _start(api_client, exam_id, headers=student).json()["attempt"]["attempt_id"]
    sub_id = _submit(api_client, exam_id, aid, {"m1": "right", "l1": "essay"}).json()["submission_id"]

    [row] = api_client.get("/api/v1/student/results", headers=student).json()
    assert row["status"] == "pending_review" and row["exam_name"] == "Mid-term" and row["exam_type"] == "MSE"
    assert (row["graded_marks"], row["graded_max_marks"]) == (2, 2)
    assert (row["pending_review_marks"], row["pending_review_count"], row["total_max_marks"]) == (8, 1, 10)
    assert row["final_marks"] is None and row["grade"] is None

    assert api_client.patch(f"/api/v1/exams/{exam_id}/submissions/{sub_id}/answers/l1",
                            json={"marks_awarded": 6, "feedback": "Solid"}).status_code == 200
    [row] = api_client.get("/api/v1/student/results", headers=student).json()
    assert row["status"] == "graded" and row["final_marks"] == 8 and row["final_percent"] == 80.0
    assert row["grade"] == "A+" and row["pending_review_count"] == 0
    assert _keys(row) & FORBIDDEN == set()
    assert "Solid" not in json.dumps(row) and "essay" not in json.dumps(row)


def test_results_only_include_the_accounts_own_linked_submissions(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1), duration=30)
    # Someone takes the exam via the plain link under a roll number...
    aid = _start(api_client, exam_id, name="Ben", roll="CS-102").json()["attempt"]["attempt_id"]
    _submit(api_client, exam_id, aid, {"m1": "right"}, name="Ben")
    # ...then an account with that roll number is created: the unverified link
    # submission is not shown as theirs (status says submitted, no score).
    ben = _student(api_client, name="Ben", roll="CS-102", email="ben@student.test")
    _join(api_client, ben, _join_code(api_client))
    assert api_client.get("/api/v1/student/results", headers=ben).json() == []
    assert _exams(api_client, ben)[0]["my_status"] == "submitted"
    # And another student sees nothing of Ben's.
    asha = _student(api_client)
    assert api_client.get("/api/v1/student/results", headers=asha).json() == []


def test_teacher_results_api_unchanged_for_dashboard_attempts(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0 - timedelta(minutes=1), duration=30)
    student = _student(api_client)
    aid = _start(api_client, exam_id, headers=student).json()["attempt"]["attempt_id"]
    _submit(api_client, exam_id, aid, {"m1": "right"})
    [sub] = api_client.get(f"/api/v1/exams/{exam_id}/submissions").json()
    assert sub["student_name"] == "Asha Rao" and sub["student_identifier"] == "CS-101"
    assert sub["answers"][0]["correct"] is True and sub["total_marks_awarded"] == 2
