"""The student-facing submit response is a trimmed receipt: auto-graded score
plus marks pending teacher review, with no answer key, per-question
correctness, grading detail or question metadata. The teacher's results API
keeps the full graded submission."""

import json
from datetime import timedelta

from app.schemas.bloom import BloomLevel
from app.schemas.question import QuestionType
from tests.conftest import T0
from tests.factories import make_exam, q, seed

MCQ, LONG, SHORT, CODE = QuestionType.MCQ, QuestionType.LONG_ANSWER, QuestionType.SHORT_ANSWER, QuestionType.CODE_FIX

# Anything that grades, explains or describes a question must not reach the student.
FORBIDDEN_KEYS = {
    "correct", "detail", "correct_answer", "test_cases", "test_cases_passed", "test_cases_total",
    "difficulty_score", "topic_ids", "bloom_level", "skill_category", "marks_awarded", "max_marks",
    "manually_graded", "feedback", "answer", "fully_auto_graded", "total_marks_awarded", "password",
}


def _all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _all_keys(v)}
    return set()


def _mixed_exam(api_client, **kwargs) -> str:
    seed(api_client, [
        q("m1", MCQ, 2, BloomLevel.REMEMBER),
        q("m2", MCQ, 3, BloomLevel.REMEMBER),
        q("c1", CODE, 4, BloomLevel.APPLY),
        q("s1", SHORT, 2),
        q("l1", LONG, 10, BloomLevel.EVALUATE),
    ])
    return make_exam(api_client, ["m1", "m2", "c1", "s1", "l1"], go_live=T0 - timedelta(minutes=1), **kwargs)


def _submit(api_client, exam_id, answers: dict, **extra):
    body = {"student_name": "Asha", "student_identifier": "R01",
            "answers": [{"question_id": k, "answer": v} for k, v in answers.items()], **extra}
    return api_client.post(f"/api/v1/exams/{exam_id}/submit", json=body)


def test_receipt_shows_auto_graded_score_and_pending_marks(api_client, clock):
    exam_id = _mixed_exam(api_client)
    r = _submit(api_client, exam_id, {
        "m1": "right", "m2": "wrong",
        "c1": "print(int(input()) + 2)",  # passes 1 of 2 tests
        "s1": "a stack is LIFO", "l1": "an essay",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_graded_marks"] == 2 + 0 + 2
    assert body["auto_graded_max_marks"] == 2 + 3 + 4
    assert body["pending_review_marks"] == 12  # never counted as zero
    assert body["pending_review_count"] == 2
    assert body["total_max_marks"] == 21
    assert body["student_name"] == "Asha" and body["exam_id"] == exam_id
    assert body["auto_submitted"] is False
    assert {a["question_id"]: a["status"] for a in body["answers"]} == {
        "m1": "auto_graded", "m2": "auto_graded", "c1": "auto_graded",
        "s1": "pending_review", "l1": "pending_review",
    }


def test_receipt_hides_answer_key_correctness_and_metadata(api_client, clock):
    exam_id = _mixed_exam(api_client)
    body = _submit(api_client, exam_id, {"m1": "right", "s1": "text"}).json()
    leaked = _all_keys(body) & FORBIDDEN_KEYS
    assert leaked == set()
    # Only these per-question fields, nothing else.
    assert all(set(a) == {"question_id", "status"} for a in body["answers"])
    # And no correct-answer values smuggled in anywhere.
    assert "print(int(input()) * 2)" not in json.dumps(body)




def test_teacher_results_api_keeps_full_submission(api_client, clock):
    exam_id = _mixed_exam(api_client)
    receipt = _submit(api_client, exam_id, {"m1": "right", "l1": "essay"}).json()
    subs = api_client.get(f"/api/v1/exams/{exam_id}/submissions").json()
    assert len(subs) == 1 and subs[0]["id"] == receipt["submission_id"]
    sub = subs[0]
    assert sub["total_marks_awarded"] == 2 and sub["fully_auto_graded"] is False
    answers = {a["question_id"]: a for a in sub["answers"]}
    assert answers["m1"]["correct"] is True and answers["m1"]["detail"] == "Correct"
    assert answers["m1"]["topic_ids"] == ["stacks"] and answers["m1"]["bloom_level"] == 1
    assert answers["m1"]["difficulty_score"] == 5.0
    assert answers["l1"]["answer"] == "essay" and answers["l1"]["correct"] is None
    assert answers["c1"]["test_cases_total"] == 2


def test_receipt_for_timed_attempt(api_client, clock):
    exam_id = _mixed_exam(api_client, duration=30)
    started = api_client.post(f"/api/v1/exams/{exam_id}/start",
                              json={"student_name": "Asha", "student_identifier": "R01"}).json()["attempt"]
    api_client.put(f"/api/v1/exams/{exam_id}/attempts/{started['attempt_id']}/answers",
                   json={"answers": [{"question_id": "m2", "answer": "right"}], "seq": 1})
    clock.advance(minutes=5)
    r = _submit(api_client, exam_id, {"m1": "right"}, attempt_id=started["attempt_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attempt_id"] == started["attempt_id"]
    assert body["started_at"].startswith("2026-10-01T09:00")
    assert body["submitted_at"].startswith("2026-10-01T09:05")
    assert body["auto_graded_marks"] == 5  # m1 from the request + m2 from the autosave
    assert _all_keys(body) & FORBIDDEN_KEYS == set()


def test_receipt_when_everything_needs_manual_grading(api_client, clock):
    seed(api_client, [q("s1", SHORT, 3), q("l1", LONG, 7)])
    exam_id = make_exam(api_client, ["s1", "l1"], go_live=T0 - timedelta(minutes=1))
    body = _submit(api_client, exam_id, {"s1": "x"}).json()
    assert body["auto_graded_marks"] == 0 and body["auto_graded_max_marks"] == 0
    assert body["pending_review_marks"] == 10 and body["pending_review_count"] == 2


def test_questions_served_during_attempt_hide_answer_key(api_client, clock):
    """/start and attempt status (resume) serve questions without answer keys,
    hidden code test cases or internal metadata."""
    exam_id = _mixed_exam(api_client, duration=30)
    assert api_client.patch(f"/api/v1/exams/{exam_id}", json={"password": "pw"}).status_code == 200
    start = api_client.post(f"/api/v1/exams/{exam_id}/start",
                            json={"student_name": "Asha", "student_identifier": "R01", "password": "pw"})
    assert start.status_code == 200, start.text
    aid = start.json()["attempt"]["attempt_id"]
    status = api_client.get(f"/api/v1/exams/{exam_id}/attempts/{aid}")
    for body in (start.json(), status.json()):
        assert len(body["exam"]["questions"]) == 5
        leaked = _all_keys(body) & {"correct_answer", "test_cases", "expected_output", "difficulty_score",
                                    "topic_ids", "co_ids", "provenance", "skill_category", "password"}
        assert leaked == set()
        code = next(q for q in body["exam"]["questions"] if q["id"] == "c1")
        assert code["starter_code"] == "print(int(input()) + 1)"
        assert "print(int(input()) * 2)" not in json.dumps(body)
