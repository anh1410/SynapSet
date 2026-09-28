from datetime import UTC, datetime, timedelta

from app.schemas.bloom import BloomLevel
from app.schemas.exam import Exam
from app.schemas.question import CodeTestCase, Question, QuestionType
from app.schemas.skill import SkillCategory, resolve_skill_category
from app.schemas.submission import GradedAnswer, Submission
from app.services.performance_analytics import (
    band_for,
    class_overview,
    grade_for,
    latest_attempts,
    student_detail,
    student_key,
)

T0 = datetime(2026, 9, 1, tzinfo=UTC)


# ---------- classification & grading scale ----------


def test_skill_category_derived_from_existing_metadata():
    assert resolve_skill_category("code_fix", 1) == SkillCategory.CODING
    assert resolve_skill_category("mcq", int(BloomLevel.REMEMBER)) == SkillCategory.CONCEPTUAL
    assert resolve_skill_category("short_answer", int(BloomLevel.UNDERSTAND)) == SkillCategory.CONCEPTUAL
    assert resolve_skill_category("long_answer", int(BloomLevel.ANALYZE)) == SkillCategory.REASONING
    # Teacher override wins.
    assert resolve_skill_category("numerical", 1, "reasoning") == SkillCategory.REASONING


def test_question_effective_skill_category():
    q = Question(id="q", text="t", question_type=QuestionType.NUMERICAL, marks=2, bloom_level=BloomLevel.APPLY)
    assert q.effective_skill_category == SkillCategory.REASONING


def test_grade_scale_and_bands():
    assert grade_for(95) == ("O", "Outstanding")
    assert grade_for(72.5)[0] == "A"
    assert grade_for(40)[0] == "P"
    assert grade_for(39.9)[0] == "F"
    assert grade_for(None) is None
    assert band_for(80, 5) == "strong"
    assert band_for(60, 5) == "developing"
    assert band_for(20, 5) == "needs_support"
    assert band_for(100, 1) == "insufficient"  # not enough evidence to call it


# ---------- fixtures built from real-shaped data ----------


def _exam(eid, name, exam_type="QUIZ", day=0):
    return Exam(id=eid, teacher_id="t", subject_id="s", name=name, exam_type=exam_type, go_live_at=T0 + timedelta(days=day))


def _ans(qid, qtype, bloom, awarded, max_marks, topics, graded=True, tests=None):
    return GradedAnswer(
        question_id=qid,
        question_type=qtype,
        auto_graded=graded,
        correct=None,
        marks_awarded=awarded,
        max_marks=max_marks,
        detail="",
        bloom_level=int(bloom),
        topic_ids=topics,
        difficulty_score=5.0,
        test_cases_passed=tests[0] if tests else None,
        test_cases_total=tests[1] if tests else None,
    )


def _sub(sid, exam_id, name, ident, answers, day=0):
    s = Submission(
        id=sid,
        exam_id=exam_id,
        student_name=name,
        student_identifier=ident,
        answers=answers,
        total_marks_awarded=0,
        total_max_marks=0,
        fully_auto_graded=False,
        submitted_at=T0 + timedelta(days=day, hours=1),
    )
    s.recompute_totals()
    return s


def _dataset():
    exams = [_exam("e1", "Quiz 1", day=0), _exam("e2", "MSE", "MSE", day=7)]
    subs = [
        # Asha: strong concepts, weak coding.
        _sub("s1", "e1", "Asha", "R01", [
            _ans("q1", QuestionType.MCQ, BloomLevel.REMEMBER, 2, 2, ["stacks"]),
            _ans("q2", QuestionType.CODE_FIX, BloomLevel.APPLY, 1, 4, ["recursion"], tests=(1, 4)),
        ]),
        _sub("s2", "e2", "Asha", "R01", [
            _ans("q3", QuestionType.SHORT_ANSWER, BloomLevel.UNDERSTAND, 5, 5, ["stacks"]),
            _ans("q4", QuestionType.LONG_ANSWER, BloomLevel.ANALYZE, 0, 10, ["recursion"], graded=False),
        ], day=7),
        # Ben: one quiz, all right.
        _sub("s3", "e1", "Ben", "R02", [
            _ans("q1", QuestionType.MCQ, BloomLevel.REMEMBER, 2, 2, ["stacks"]),
            _ans("q2", QuestionType.CODE_FIX, BloomLevel.APPLY, 4, 4, ["recursion"], tests=(4, 4)),
        ]),
    ]
    return exams, subs


def test_latest_attempt_per_student_per_exam():
    exams, subs = _dataset()
    retake = _sub("s1b", "e1", "Asha", "r01", [_ans("q1", QuestionType.MCQ, BloomLevel.REMEMBER, 0, 2, ["stacks"])], day=1)
    latest = latest_attempts(subs + [retake])
    asha_e1 = [s for s in latest if student_key(s) == "id:r01" and s.exam_id == "e1"]
    assert [s.id for s in asha_e1] == ["s1b"]


def test_class_overview_uses_only_graded_marks():
    exams, subs = _dataset()
    ov = class_overview(exams, subs, {}, {"stacks": "Stacks", "recursion": "Recursion"})
    assert ov.summary.students == 2
    assert ov.summary.assessments == 2
    assert ov.summary.pending_answers == 1
    # Asha: (2+1+5)/(2+4+5) = 72.7 (pending 10-marker excluded, not zeroed); Ben: 6/6 = 100.
    by_name = {s.name: s for s in ov.students}
    assert by_name["Asha"].percent == 72.7
    assert by_name["Asha"].grade.grade == "A"
    assert by_name["Ben"].percent == 100.0
    assert ov.summary.average_percent == 86.3

    skills = {row.skill: row.score for row in ov.breakdowns.skills}
    assert skills[SkillCategory.CODING].percent == 62.5  # (1+4)/(4+4)
    assert skills[SkillCategory.CONCEPTUAL].percent == 100.0
    # The only reasoning answer is still pending: no percent, not zero.
    assert skills[SkillCategory.REASONING].percent is None
    assert skills[SkillCategory.REASONING].pending == 1

    assert ov.breakdowns.coding_tests.passed == 5
    assert ov.breakdowns.coding_tests.total == 8
    topics = {row.key: row for row in ov.breakdowns.topics}
    assert topics["stacks"].label == "Stacks"
    assert topics["stacks"].band == "strong"
    assert [p.name for p in ov.trend] == ["Quiz 1", "MSE"]
    assert sum(b.count for b in ov.score_histogram) == 2


def test_student_detail_history_rank_and_breakdowns():
    exams, subs = _dataset()
    detail = student_detail("id:r01", exams, subs, {}, {})
    assert detail.name == "Asha"
    assert [h.name for h in detail.history] == ["Quiz 1", "MSE"]
    assert detail.history[0].percent == 50.0
    assert detail.history[0].class_average_percent == 75.0
    assert detail.history[1].pending == 1
    assert detail.summary.rank == 2
    assert detail.summary.class_size == 2
    weak = [r.key for r in detail.breakdowns.weaknesses]
    assert weak == []  # recursion has only 1 graded answer -> insufficient evidence, not a weakness
    assert student_detail("id:nobody", exams, subs, {}, {}) is None


def test_old_submissions_fall_back_to_question_bank():
    exams = [_exam("e1", "Quiz 1")]
    legacy = GradedAnswer(
        question_id="q1", question_type=QuestionType.MCQ, auto_graded=True, correct=True,
        marks_awarded=2, max_marks=2, detail="Correct",
    )
    subs = [_sub("s1", "e1", "Old", None, [legacy])]
    bank = {"q1": Question(id="q1", text="t", question_type=QuestionType.MCQ, marks=2,
                           bloom_level=BloomLevel.ANALYZE, topic_ids=["graphs"])}
    ov = class_overview(exams, subs, bank, {})
    assert ov.breakdowns.bloom[0].label == "Analyze"
    assert ov.breakdowns.topics[0].key == "graphs"


# ---------- API: submission snapshot, manual grading, analytics, isolation ----------


def _live_exam(api_client, question_ids, exam_type="QUIZ"):
    r = api_client.post(
        "/api/v1/exams",
        json={"subject_id": api_client.subject_id, "name": "Test", "question_ids": question_ids, "exam_type": exam_type},
    )
    exam_id = r.json()["id"]
    api_client.patch(f"/api/v1/exams/{exam_id}", json={"go_live_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()})
    return exam_id


def _seed(api_client):
    from app.core.question_bank import get_question_bank

    get_question_bank(api_client.subject_id).add_many([
        Question(id="mcq", text="2+2?", question_type=QuestionType.MCQ, marks=2, bloom_level=BloomLevel.REMEMBER,
                 options=["3", "4"], correct_answer="4", topic_ids=["arith"]),
        Question(id="essay", text="Explain.", question_type=QuestionType.LONG_ANSWER, marks=10,
                 bloom_level=BloomLevel.EVALUATE, topic_ids=["arith"]),
        Question(id="code", text="Fix", question_type=QuestionType.CODE_FIX, marks=4, bloom_level=BloomLevel.APPLY,
                 code_language="python", starter_code="print(int(input())+1)", correct_answer="print(int(input())*2)",
                 test_cases=[CodeTestCase(input="2\n", expected_output="4"), CodeTestCase(input="3\n", expected_output="6")]),
    ])


def test_submission_snapshots_answer_and_metadata(api_client):
    _seed(api_client)
    exam_id = _live_exam(api_client, ["mcq", "essay", "code"])
    r = api_client.post(f"/api/v1/exams/{exam_id}/submit", json={
        "student_name": "Asha", "student_identifier": "R01",
        "answers": [
            {"question_id": "mcq", "answer": "4"},
            {"question_id": "essay", "answer": "Because..."},
            {"question_id": "code", "answer": "print(int(input())+2)"},
        ],
    })
    assert r.status_code == 200
    # The snapshot lives on the teacher's view (the student only gets a trimmed receipt).
    sub = api_client.get(f"/api/v1/exams/{exam_id}/submissions").json()[0]
    answers = {a["question_id"]: a for a in sub["answers"]}
    assert answers["essay"]["answer"] == "Because..."
    assert answers["essay"]["skill_category"] == "reasoning"
    assert answers["mcq"]["skill_category"] == "conceptual"
    assert answers["code"]["skill_category"] == "coding"
    assert answers["code"]["test_cases_passed"] == 1  # 2+2 == 4 happens to pass; 3+2 != 6
    assert answers["code"]["test_cases_total"] == 2
    assert answers["mcq"]["topic_ids"] == ["arith"]
    assert sub["fully_auto_graded"] is False


def test_manual_grading_updates_totals_and_analytics(api_client):
    _seed(api_client)
    exam_id = _live_exam(api_client, ["mcq", "essay"], exam_type="MSE")
    receipt = api_client.post(f"/api/v1/exams/{exam_id}/submit", json={
        "student_name": "Asha", "student_identifier": "R01",
        "answers": [{"question_id": "mcq", "answer": "4"}, {"question_id": "essay", "answer": "..."}],
    }).json()
    sub = {"id": receipt["submission_id"]}

    ov = api_client.get(f"/api/v1/analytics/overview?subject_id={api_client.subject_id}").json()
    assert ov["summary"]["pending_answers"] == 1
    assert ov["students"][0]["percent"] == 100.0  # only the graded MCQ counts so far

    r = api_client.patch(f"/api/v1/exams/{exam_id}/submissions/{sub['id']}/answers/essay",
                         json={"marks_awarded": 11})
    assert r.status_code == 422
    r = api_client.patch(f"/api/v1/exams/{exam_id}/submissions/{sub['id']}/answers/essay",
                         json={"marks_awarded": 6, "feedback": "Good start"})
    assert r.status_code == 200
    body = r.json()
    assert body["total_marks_awarded"] == 8
    assert body["fully_auto_graded"] is True
    essay = next(a for a in body["answers"] if a["question_id"] == "essay")
    assert essay["manually_graded"] is True and essay["correct"] is None and essay["feedback"] == "Good start"

    ov = api_client.get(f"/api/v1/analytics/overview?subject_id={api_client.subject_id}").json()
    assert ov["summary"]["pending_answers"] == 0
    assert ov["students"][0]["percent"] == 66.7  # 8/12
    assert ov["assessments"][0]["exam_type"] == "MSE"

    key = ov["students"][0]["key"]
    r = api_client.get(f"/api/v1/analytics/students/{key}?subject_id={api_client.subject_id}")
    assert r.status_code == 200
    assert r.json()["summary"]["grade"]["grade"] == "B+"

    # Exam-type filter.
    quiz_only = api_client.get(f"/api/v1/analytics/overview?subject_id={api_client.subject_id}&exam_type=QUIZ").json()
    assert quiz_only["summary"]["students"] == 0


def test_analytics_isolated_between_teachers(api_client):
    _seed(api_client)
    exam_id = _live_exam(api_client, ["mcq"])
    api_client.post(f"/api/v1/exams/{exam_id}/submit", json={
        "student_name": "Asha", "answers": [{"question_id": "mcq", "answer": "4"}],
    })
    other = api_client.post(
        "/api/v1/auth/signup", json={"email": "other@test.local", "password": "another-password-1", "name": "Other"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {other}"}
    sid = api_client.subject_id
    assert api_client.get(f"/api/v1/analytics/overview?subject_id={sid}", headers=headers).status_code == 404
    assert api_client.get(f"/api/v1/analytics/students/name:asha?subject_id={sid}", headers=headers).status_code == 404

    own_subject = api_client.post("/api/v1/subjects", json={"name": "Mine"}, headers=headers).json()["id"]
    ov = api_client.get(f"/api/v1/analytics/overview?subject_id={own_subject}", headers=headers).json()
    assert ov["summary"]["students"] == 0
    assert ov["students"] == []
