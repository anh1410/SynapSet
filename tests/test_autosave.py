"""Server-side autosave on timed attempts: restore after reconnect, stale
saves ignored, deadline/closing respected (never extended), final submit
merges saved answers, and ended attempts are finalised from saved answers."""

from datetime import timedelta

import pytest

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from tests.conftest import T0
from tests.factories import make_exam, other_teacher_headers, q, seed

MCQ = QuestionType.MCQ


@pytest.fixture
def timed(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2, BloomLevel.REMEMBER), q("m2", MCQ, 2, BloomLevel.REMEMBER)])
    return make_exam(api_client, ["m1", "m2"], go_live=T0, duration=30)


def _start(api_client, exam_id, name="Asha", ident="R01"):
    r = api_client.post(f"/api/v1/exams/{exam_id}/start", json={"student_name": name, "student_identifier": ident})
    assert r.status_code == 200, r.text
    return r.json()


def _save(api_client, exam_id, attempt_id, answers: dict, seq=None):
    body = {"answers": [{"question_id": k, "answer": v} for k, v in answers.items()]}
    if seq is not None:
        body["seq"] = seq
    return api_client.put(f"/api/v1/exams/{exam_id}/attempts/{attempt_id}/answers", json=body)


def test_autosave_then_restore_after_reconnect(api_client, clock, timed):
    a = _start(api_client, timed)
    aid = a["attempt"]["attempt_id"]
    assert a["saved_answers"] == {}
    r = _save(api_client, timed, aid, {"m1": "right"}, seq=1)
    assert r.status_code == 200 and r.json()["applied"] is True and r.json()["saved_count"] == 1
    clock.advance(minutes=5)
    _save(api_client, timed, aid, {"m2": "wrong"}, seq=2)

    # Refresh: start again, and the status endpoint - both return the saved answers.
    again = _start(api_client, timed, name="asha", ident="r01")
    assert again["attempt"]["attempt_id"] == aid
    assert again["saved_answers"] == {"m1": "right", "m2": "wrong"} and again["save_seq"] == 2
    status = api_client.get(f"/api/v1/exams/{timed}/attempts/{aid}").json()
    assert status["saved_answers"] == {"m1": "right", "m2": "wrong"}
    assert status["last_saved_at"].startswith("2026-10-01T09:05")


def test_stale_or_replayed_save_is_ignored(api_client, clock, timed):
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "newest"}, seq=5)
    late = _save(api_client, timed, aid, {"m1": "older"}, seq=3)  # retry arriving after reconnect
    assert late.status_code == 200 and late.json()["applied"] is False
    assert api_client.get(f"/api/v1/exams/{timed}/attempts/{aid}").json()["saved_answers"]["m1"] == "newest"


def test_unknown_question_ids_are_not_saved(api_client, clock, timed):
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "right", "injected": "x"})
    assert api_client.get(f"/api/v1/exams/{timed}/attempts/{aid}").json()["saved_answers"] == {"m1": "right"}


def test_autosave_respects_deadline_and_never_extends_it(api_client, clock, timed):
    a = _start(api_client, timed)
    aid, deadline = a["attempt"]["attempt_id"], a["attempt"]["deadline"]
    clock.advance(minutes=29)
    r = _save(api_client, timed, aid, {"m1": "right"})
    assert r.status_code == 200 and r.json()["deadline"] == deadline  # saving didn't move it
    clock.advance(minutes=2)  # past deadline + 30s grace
    late = _save(api_client, timed, aid, {"m2": "right"})
    assert late.status_code == 403 and "Time is up" in late.json()["detail"]


def test_autosave_respects_closing_time(api_client, clock):
    seed(api_client, [q("m1", MCQ, 2)])
    exam_id = make_exam(api_client, ["m1"], go_live=T0, duration=30, closes=T0 + timedelta(minutes=10))
    aid = _start(api_client, exam_id)["attempt"]["attempt_id"]
    clock.advance(minutes=11)
    assert _save(api_client, exam_id, aid, {"m1": "right"}).status_code == 403


def test_submit_uses_latest_saved_answers(api_client, clock, timed):
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "right", "m2": "wrong"})
    # Final submit only sends m2 (just changed); m1 comes from the autosave.
    r = api_client.post(f"/api/v1/exams/{timed}/submit", json={
        "student_name": "Asha", "attempt_id": aid, "answers": [{"question_id": "m2", "answer": "right"}]})
    assert r.status_code == 200
    assert r.json()["auto_graded_marks"] == 4 and r.json()["auto_submitted"] is False
    sub = api_client.get(f"/api/v1/exams/{timed}/submissions").json()[0]
    answers = {a["question_id"]: a["answer"] for a in sub["answers"]}
    assert answers == {"m1": "right", "m2": "right"} and sub["total_marks_awarded"] == 4
    # One attempt per student: no more saving or starting.
    assert _save(api_client, timed, aid, {"m1": "x"}).status_code == 409
    assert api_client.post(f"/api/v1/exams/{timed}/start", json={"student_name": "Asha", "student_identifier": "R01"}).status_code == 409


def test_timed_out_attempt_is_finalised_from_saved_answers(api_client, clock, timed):
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "right"})
    empty = _start(api_client, timed, name="Ben", ident="R02")["attempt"]["attempt_id"]  # never saves anything
    clock.advance(minutes=45)

    subs = api_client.get(f"/api/v1/exams/{timed}/submissions").json()
    assert len(subs) == 1
    s = subs[0]
    assert s["student_name"] == "Asha" and s["auto_submitted"] is True and s["total_marks_awarded"] == 2
    assert s["submitted_at"].startswith("2026-10-01T09:30")  # stamped at the deadline, not when noticed
    rows = {a["student_name"]: a for a in api_client.get(f"/api/v1/exams/{timed}/attempts").json()}
    assert rows["Asha"]["status"] == "submitted"
    assert rows["Ben"]["status"] == "timed_out" and rows["Ben"]["saved_answer_count"] == 0
    # A late submit is refused, and the finalised attempt can't be resumed.
    late = api_client.post(f"/api/v1/exams/{timed}/submit", json={"student_name": "Ben", "attempt_id": empty, "answers": []})
    assert late.status_code == 403
    resumed = api_client.post(f"/api/v1/exams/{timed}/start", json={"student_name": "Asha", "student_identifier": "R01"})
    assert resumed.status_code == 403 and "submitted automatically" in resumed.json()["detail"]
    # Finalisation is idempotent.
    assert len(api_client.get(f"/api/v1/exams/{timed}/submissions").json()) == 1


def test_late_actions_on_auto_submitted_attempt_explain_what_happened(api_client, clock, timed):
    """Regression: once a late autosave triggers finalisation, the student's
    late submit used to get 409 "You have already submitted" - misleading,
    since the server submitted for them. It must say time ran out and their
    saved answers were submitted automatically."""
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "right"})
    clock.advance(minutes=31)
    assert _save(api_client, timed, aid, {"m2": "right"}).status_code == 403  # finalises the attempt
    for r in (
        api_client.post(f"/api/v1/exams/{timed}/submit", json={"student_name": "Asha", "attempt_id": aid, "answers": []}),
        _save(api_client, timed, aid, {"m2": "right"}),
        api_client.post(f"/api/v1/exams/{timed}/start", json={"student_name": "Asha", "student_identifier": "R01"}),
    ):
        assert r.status_code == 403
        assert "submitted automatically" in r.json()["detail"]
    # Submitting late without having saved first (nothing to finalise) still just says time is up.
    bid = _start(api_client, timed, name="Ben", ident="R02")["attempt"]["attempt_id"]
    clock.advance(minutes=40)
    r = api_client.post(f"/api/v1/exams/{timed}/submit", json={"student_name": "Ben", "attempt_id": bid, "answers": []})
    assert r.status_code == 403 and "Time is up" in r.json()["detail"]


def test_manual_close_finalises_in_progress_saved_work(api_client, clock, timed):
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "right", "m2": "right"})
    api_client.patch(f"/api/v1/exams/{timed}", json={"status": "closed"})
    assert _save(api_client, timed, aid, {"m1": "x"}).status_code in (403, 409)
    subs = api_client.get(f"/api/v1/exams/{timed}/submissions").json()
    assert len(subs) == 1 and subs[0]["auto_submitted"] is True and subs[0]["total_marks_awarded"] == 4


def test_finalised_attempts_count_in_analytics(api_client, clock, timed):
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    _save(api_client, timed, aid, {"m1": "right"})
    clock.advance(hours=1)
    a = api_client.get(f"/api/v1/analytics/exams/{timed}").json()
    assert a["participation"]["auto_submitted"] == 1 and a["summary"]["students"] == 1


def test_autosave_token_scoped_to_its_exam(api_client, clock, timed):
    seed(api_client, [q("z1", MCQ, 1)])
    other = make_exam(api_client, ["z1"], go_live=T0, duration=30)
    aid = _start(api_client, timed)["attempt"]["attempt_id"]
    assert _save(api_client, other, aid, {"z1": "right"}).status_code == 404
    # Teacher-side views stay per-teacher.
    assert api_client.get(f"/api/v1/exams/{timed}/attempts", headers=other_teacher_headers(api_client)).status_code == 404
