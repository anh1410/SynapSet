"""Exam scheduling: go-live / closing times, server-side attempts and duration
enforcement, student-facing timing info, and teacher access control.

Time is controlled through app.core.clock so the tests never sleep."""

from datetime import datetime, timedelta

from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from tests.conftest import T0


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _exam(api_client, *, go_live=None, closes=None, duration=30, password="pw"):
    from app.core.question_bank import get_question_bank

    get_question_bank(api_client.subject_id).add(
        Question(id="mcq", text="2+2?", question_type=QuestionType.MCQ, marks=2,
                 bloom_level=BloomLevel.REMEMBER, options=["3", "4"], correct_answer="4")
    )
    r = api_client.post("/api/v1/exams", json={
        "subject_id": api_client.subject_id, "name": "Timed quiz", "question_ids": ["mcq"],
        "total_marks": 2, "duration_minutes": duration,
    })
    assert r.status_code == 200, r.text
    exam_id = r.json()["id"]
    update = {"password": password}
    if go_live is not None:
        update["go_live_at"] = _iso(go_live)
    if closes is not None:
        update["closes_at"] = _iso(closes)
    r = api_client.patch(f"/api/v1/exams/{exam_id}", json=update)
    assert r.status_code == 200, r.text
    return exam_id


def _start(api_client, exam_id, name="Asha", ident="R01", password="pw"):
    return api_client.post(f"/api/v1/exams/{exam_id}/start",
                           json={"password": password, "student_name": name, "student_identifier": ident})


def _submit(api_client, exam_id, attempt_id=None, name="Asha", ident="R01", answer="4", password="pw"):
    body = {"password": password, "student_name": name, "student_identifier": ident,
            "answers": [{"question_id": "mcq", "answer": answer}]}
    if attempt_id:
        body["attempt_id"] = attempt_id
    return api_client.post(f"/api/v1/exams/{exam_id}/submit", json=body)


def _bucket(api_client, exam_id):
    return api_client.get(f"/api/v1/exams/{exam_id}").json()["exam"]


# ---------- schedule states ----------


def test_scheduled_exam_before_go_live(api_client, clock):
    exam_id = _exam(api_client, go_live=T0 + timedelta(hours=2))
    assert _bucket(api_client, exam_id)["bucket"] == "upcoming"

    t = api_client.get(f"/api/v1/exams/{exam_id}/timing").json()
    assert t["state"] == "upcoming"
    assert t["opens_in_seconds"] == 2 * 3600
    assert t["duration_minutes"] == 30
    assert t["closes_at"] is None

    assert _start(api_client, exam_id).status_code == 403
    assert api_client.post(f"/api/v1/exams/{exam_id}/verify-password", json={"password": "pw"}).status_code == 403
    assert _submit(api_client, exam_id).status_code == 403


def test_exam_becomes_live_at_go_live_time(api_client, clock):
    exam_id = _exam(api_client, go_live=T0 + timedelta(minutes=10))
    clock.advance(minutes=10)
    assert _bucket(api_client, exam_id)["bucket"] == "live"
    assert api_client.get(f"/api/v1/exams/{exam_id}/timing").json()["state"] == "live"

    r = _start(api_client, exam_id)
    assert r.status_code == 200
    body = r.json()
    assert body["attempt"]["remaining_seconds"] == 30 * 60
    assert [q["id"] for q in body["exam"]["questions"]] == ["mcq"]
    assert "correct_answer" not in str(body)  # no answer key leaks


def test_draft_exam_is_invisible_to_students(api_client, clock):
    exam_id = _exam(api_client)  # no go-live time -> draft
    assert api_client.get(f"/api/v1/exams/{exam_id}/timing").status_code == 404
    assert _start(api_client, exam_id).status_code == 404


def test_automatic_closure_at_closing_time(api_client, clock):
    exam_id = _exam(api_client, go_live=T0, closes=T0 + timedelta(hours=1))
    t = api_client.get(f"/api/v1/exams/{exam_id}/timing").json()
    assert t["state"] == "live" and t["closes_in_seconds"] == 3600

    clock.advance(hours=1)
    exam = _bucket(api_client, exam_id)
    assert exam["bucket"] == "closed"
    assert exam["closed_by"] == "schedule"
    assert exam["status"] == "scheduled"  # closed by time, not by the teacher
    t = api_client.get(f"/api/v1/exams/{exam_id}/timing").json()
    assert t["state"] == "closed" and t["closed_by"] == "schedule"
    assert _start(api_client, exam_id).status_code == 403


def test_manual_close_still_works(api_client, clock):
    exam_id = _exam(api_client, go_live=T0, closes=T0 + timedelta(days=1))
    attempt_id = _start(api_client, exam_id).json()["attempt"]["attempt_id"]

    r = api_client.patch(f"/api/v1/exams/{exam_id}", json={"status": "closed"})
    assert r.status_code == 200
    assert r.json()["bucket"] == "closed" and r.json()["closed_by"] == "teacher"

    # A student mid-attempt can no longer submit, and no questions are handed out.
    assert _submit(api_client, exam_id, attempt_id).status_code == 403
    resumed = _start(api_client, exam_id).json()
    assert resumed["timing"]["closed_by"] == "teacher"
    assert resumed["exam"] is None
    assert _start(api_client, exam_id, name="New", ident="R99").status_code == 403


def test_missing_closing_time_stays_open(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    clock.advance(days=30)
    assert _bucket(api_client, exam_id)["bucket"] == "live"
    t = api_client.get(f"/api/v1/exams/{exam_id}/timing").json()
    assert t["closes_at"] is None and t["closes_in_seconds"] is None
    assert _start(api_client, exam_id).status_code == 200


# ---------- duration enforcement ----------


def test_submission_before_duration_expires(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    started = _start(api_client, exam_id).json()["attempt"]
    clock.advance(minutes=29)
    r = _submit(api_client, exam_id, started["attempt_id"])
    assert r.status_code == 200, r.text
    sub = r.json()
    assert sub["attempt_id"] == started["attempt_id"]
    assert sub["started_at"].startswith("2026-10-01T09:00")
    assert sub["total_marks_awarded"] == 2


def test_submission_within_network_grace_is_accepted(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    attempt_id = _start(api_client, exam_id).json()["attempt"]["attempt_id"]
    clock.advance(minutes=30, seconds=20)  # 20s late, grace is 30s
    assert _submit(api_client, exam_id, attempt_id).status_code == 200


def test_submission_after_duration_expires(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    attempt_id = _start(api_client, exam_id).json()["attempt"]["attempt_id"]
    clock.advance(minutes=31)
    r = _submit(api_client, exam_id, attempt_id)
    assert r.status_code == 403
    assert "Time is up" in r.json()["detail"]
    status = api_client.get(f"/api/v1/exams/{exam_id}/attempts/{attempt_id}").json()
    assert status["attempt"]["expired"] is True
    assert status["attempt"]["remaining_seconds"] == 0
    assert status["exam"] is None  # questions withdrawn once time is up
    # Nothing was recorded for the teacher.
    assert api_client.get(f"/api/v1/exams/{exam_id}/submissions").json() == []


def test_submission_after_closing_time(api_client, clock):
    # Closing time falls before the 30-minute duration would end: it wins.
    exam_id = _exam(api_client, go_live=T0, closes=T0 + timedelta(minutes=20))
    started = _start(api_client, exam_id).json()["attempt"]
    assert started["remaining_seconds"] == 20 * 60
    assert started["deadline"].startswith("2026-10-01T09:20")

    clock.advance(minutes=21)
    r = _submit(api_client, exam_id, started["attempt_id"])
    assert r.status_code == 403
    assert r.json()["detail"] == "This exam is closed"


def test_attempt_started_just_before_close_keeps_until_close(api_client, clock):
    exam_id = _exam(api_client, go_live=T0, closes=T0 + timedelta(minutes=20))
    clock.advance(minutes=15)
    attempt = _start(api_client, exam_id).json()["attempt"]
    assert attempt["remaining_seconds"] == 5 * 60  # capped at closing, not the full 30
    clock.advance(minutes=4, seconds=50)
    assert _submit(api_client, exam_id, attempt["attempt_id"]).status_code == 200


def test_timed_exam_requires_start(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    r = _submit(api_client, exam_id)
    assert r.status_code == 409
    assert "Start the exam" in r.json()["detail"]


def test_untimed_exam_keeps_legacy_flow(api_client, clock):
    exam_id = _exam(api_client, go_live=T0, duration=None)
    assert api_client.post(f"/api/v1/exams/{exam_id}/verify-password", json={"password": "pw"}).status_code == 200
    r = _submit(api_client, exam_id)
    assert r.status_code == 200
    assert r.json()["attempt_id"] is None


def test_duration_is_frozen_at_start(api_client, clock):
    exam_id = _exam(api_client, go_live=T0, duration=30)
    attempt_id = _start(api_client, exam_id).json()["attempt"]["attempt_id"]
    api_client.patch(f"/api/v1/exams/{exam_id}", json={"duration_minutes": 5})
    clock.advance(minutes=20)
    assert _submit(api_client, exam_id, attempt_id).status_code == 200


# ---------- refresh / reconnect ----------


def test_refresh_resumes_same_attempt_and_timer(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    first = _start(api_client, exam_id).json()["attempt"]
    clock.advance(minutes=12)

    # Same student refreshing (identifier matched case/space-insensitively).
    again = _start(api_client, exam_id, name="asha", ident="  r01 ").json()["attempt"]
    assert again["attempt_id"] == first["attempt_id"]
    assert again["started_at"] == first["started_at"]
    assert again["remaining_seconds"] == 18 * 60

    status = api_client.get(f"/api/v1/exams/{exam_id}/attempts/{first['attempt_id']}").json()
    assert status["attempt"]["remaining_seconds"] == 18 * 60
    assert status["exam"]["questions"]

    assert _submit(api_client, exam_id, first["attempt_id"]).status_code == 200
    # After submitting: can't restart, can't resubmit, status says submitted.
    assert _start(api_client, exam_id).status_code == 409
    assert _submit(api_client, exam_id, first["attempt_id"]).status_code == 409
    done = api_client.get(f"/api/v1/exams/{exam_id}/attempts/{first['attempt_id']}").json()
    assert done["attempt"]["submitted"] is True and done["exam"] is None


def test_client_cannot_set_start_time(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    clock.advance(minutes=5)
    r = api_client.post(f"/api/v1/exams/{exam_id}/start", json={
        "password": "pw", "student_name": "Asha", "student_identifier": "R01",
        "started_at": "2099-01-01T00:00:00Z", "duration_minutes": 999,
    })
    attempt = r.json()["attempt"]
    assert attempt["started_at"].startswith("2026-10-01T09:05")
    assert attempt["remaining_seconds"] == 30 * 60


def test_submit_without_attempt_id_finds_students_attempt(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    _start(api_client, exam_id)
    clock.advance(minutes=40)
    # Omitting the attempt id doesn't dodge the deadline.
    assert _submit(api_client, exam_id).status_code == 403


def test_wrong_password_rejected_on_start(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    assert _start(api_client, exam_id, password="nope").status_code == 401


# ---------- teacher side: validation, visibility, isolation ----------


def test_closing_time_must_follow_go_live(api_client, clock):
    exam_id = _exam(api_client, go_live=T0 + timedelta(hours=1))
    r = api_client.patch(f"/api/v1/exams/{exam_id}", json={"closes_at": _iso(T0 + timedelta(minutes=30))})
    assert r.status_code == 422
    assert "Closing time must be after the go-live time" in r.json()["detail"]
    r = api_client.post("/api/v1/exams", json={
        "subject_id": api_client.subject_id, "name": "Bad", "go_live_at": _iso(T0), "closes_at": _iso(T0),
    })
    assert r.status_code == 422


def test_closing_time_can_be_cleared(api_client, clock):
    exam_id = _exam(api_client, go_live=T0, closes=T0 + timedelta(hours=1))
    r = api_client.patch(f"/api/v1/exams/{exam_id}", json={"closes_at": None})
    assert r.status_code == 200 and r.json()["closes_at"] is None


def test_teacher_sees_attempt_progress(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    a = _start(api_client, exam_id, name="Asha", ident="R01").json()["attempt"]["attempt_id"]
    _start(api_client, exam_id, name="Ben", ident="R02")
    _submit(api_client, exam_id, a)
    clock.advance(minutes=45)
    rows = {r["student_name"]: r for r in api_client.get(f"/api/v1/exams/{exam_id}/attempts").json()}
    assert rows["Asha"]["submitted"] is True
    assert rows["Ben"]["submitted"] is False and rows["Ben"]["expired"] is True


def test_scheduling_access_control_between_teachers(api_client, clock):
    exam_id = _exam(api_client, go_live=T0)
    attempt_id = _start(api_client, exam_id).json()["attempt"]["attempt_id"]
    other = api_client.post(
        "/api/v1/auth/signup", json={"email": "other@test.local", "password": "another-password-1", "name": "Other"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {other}"}
    assert api_client.patch(f"/api/v1/exams/{exam_id}", json={"closes_at": _iso(T0 + timedelta(days=1))}, headers=headers).status_code == 404
    assert api_client.get(f"/api/v1/exams/{exam_id}/attempts", headers=headers).status_code == 404
    # Teacher endpoints need auth at all.
    assert api_client.get(f"/api/v1/exams/{exam_id}/attempts", headers={"Authorization": ""}).status_code in (401, 403)

    # An attempt token only works on its own exam.
    other_exam = _exam(api_client, go_live=T0)
    assert api_client.get(f"/api/v1/exams/{other_exam}/attempts/{attempt_id}").status_code == 404
    assert _submit(api_client, other_exam, attempt_id).status_code == 404
