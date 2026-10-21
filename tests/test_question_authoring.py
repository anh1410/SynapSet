"""Teacher-written questions classified by AI (Bloom's level, topics, COs,
difficulty, duplicates, coding checks) and the code_write question type
(write the whole program / interview scenario): grading, generation, exams."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.schemas.bloom import BloomLevel
from app.schemas.generation import GeneratedQuestionDraft, QuestionDraftBatch
from app.schemas.question import CodeTestCase, Question, QuestionType
from app.services import question_analysis as qa
from app.services.grading import AUTO_GRADABLE_TYPES, grade_answer
from tests.conftest import T0
from tests.factories import make_exam, other_teacher_headers, q, seed, seed_graph

CW = QuestionType.CODE_WRITE

SUM_SOLUTION = "n = int(input())\nnums = list(map(int, input().split()))\nprint(sum(nums[:n]))"
SUM_TESTS = [{"input": "3\n1 2 3\n", "expected_output": "6"}, {"input": "2\n-1 5\n", "expected_output": "4"}]


def _fake_client(monkeypatch, draft=None, error=None, capture=None):
    def generate_content(**kw):
        if capture is not None:
            capture.append(kw["contents"])
        if error:
            raise error
        return SimpleNamespace(parsed=draft)

    monkeypatch.setattr(qa, "get_genai_client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))


def _graph(api_client):
    seed_graph(api_client, {"arrays": "Arrays", "stacks": "Stacks", "sorting": "Sorting"})
    from app.core.graph_store import get_graph_store

    gs = get_graph_store(api_client.subject_id)
    gs.add_topic("co2", name="CO2", description="Implement linear data structures")
    gs.add_relation("stacks", "co2", "MAPS_TO")
    gs.save()


def _analyze(api_client, **body):
    return api_client.post("/api/v1/questions/analyze", json={"subject_id": api_client.subject_id, **body})


# ---------- AI classification ----------


def test_analyze_maps_ai_output_onto_the_subjects_graph(api_client, monkeypatch):
    _graph(api_client)
    prompts = []
    _fake_client(monkeypatch, qa.QuestionAnalysisDraft(
        question_type="short_answer", bloom_level="ANALYZE", bloom_rationale='"Compare" asks the student to contrast two structures.',
        topic_names=["Stacks", "Arrays", "Quantum Physics"], co_codes=["CO2", "CO9"], suggested_marks=5), capture=prompts)
    r = _analyze(api_client, text="Compare a stack implemented with an array and with a linked list.")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "ai" and body["note"] is None
    assert body["bloom_level"] == 4 and "Compare" in body["bloom_rationale"]
    assert body["topic_ids"] == ["stacks", "arrays"]  # unknown topic dropped
    assert body["co_ids"] == ["CO2"]  # only COs that exist in this subject
    assert body["question_type"] == "short_answer" and body["suggested_marks"] == 5
    assert body["skill_category"] == "reasoning"
    assert 1 <= body["difficulty"]["score"] <= 10
    # The prompt lists only this subject's topics and COs, never CO nodes as topics.
    assert "- Stacks" in prompts[0] and "- CO2: Implement linear data structures" in prompts[0]
    assert "- CO2\n" not in prompts[0].split("COURSE OUTCOMES")[0]


def test_teacher_chosen_type_and_marks_win(api_client, monkeypatch):
    _graph(api_client)
    _fake_client(monkeypatch, qa.QuestionAnalysisDraft(
        question_type="long_answer", bloom_level="UNDERSTAND", bloom_rationale="x", suggested_marks=10))
    body = _analyze(api_client, text="Explain LIFO.", question_type="short_answer", marks=3).json()
    assert body["question_type"] == "short_answer" and body["suggested_marks"] == 3


def test_heuristic_fallback_when_ai_unavailable(api_client, monkeypatch):
    _graph(api_client)
    _fake_client(monkeypatch, error=RuntimeError("no API key"))
    body = _analyze(api_client, text="Compare bubble sort and merge sort on sorted input.").json()
    assert body["method"] == "heuristic" and "couldn't be reached" in body["note"]
    assert body["bloom_level"] == BloomLevel.ANALYZE and "compare" in body["bloom_rationale"]
    assert body["topic_ids"] == ["sorting"]
    assert body["question_type"] == "short_answer"


def test_heuristic_type_guess_and_coding_floor(api_client, monkeypatch):
    _graph(api_client)
    _fake_client(monkeypatch, draft=None)  # AI answered with nothing usable
    body = _analyze(api_client, text="Write a program that reads n numbers and prints their sum.").json()
    assert body["method"] == "heuristic"
    assert body["question_type"] == "code_write" and body["bloom_level"] >= BloomLevel.APPLY
    assert body["skill_category"] == "coding"


def test_duplicates_are_flagged(api_client, monkeypatch):
    _graph(api_client)
    seed(api_client, [q("dup", QuestionType.SHORT_ANSWER, 5, text="Explain the LIFO principle of a stack.", topics=("stacks",))])
    _fake_client(monkeypatch, qa.QuestionAnalysisDraft(
        question_type="short_answer", bloom_level="UNDERSTAND", bloom_rationale="Explain.", topic_names=["Stacks"], suggested_marks=4))
    body = _analyze(api_client, text="Explain the LIFO principle of a stack.").json()
    assert [m["existing_question_id"] for m in body["duplicate_matches"]] == ["dup"]


def test_analyze_validation_and_isolation(api_client, monkeypatch):
    _fake_client(monkeypatch, error=RuntimeError("x"))
    assert _analyze(api_client, text="   ").status_code == 422
    assert _analyze(api_client, text="Pick one", question_type="mcq").status_code == 422
    r = api_client.post("/api/v1/questions/analyze", headers=other_teacher_headers(api_client),
                        json={"subject_id": api_client.subject_id, "text": "Define a stack."})
    assert r.status_code == 404


# ---------- coding checks ----------


def test_reference_solution_checked_and_test_cases_computed_by_running_it(api_client, monkeypatch):
    _graph(api_client)
    # The AI proposes inputs only; expected outputs come from running the reference solution.
    _fake_client(monkeypatch, qa.QuestionAnalysisDraft(
        question_type="code_write", bloom_level="APPLY", bloom_rationale="Implement a summation.",
        topic_names=["Arrays"], suggested_marks=8, test_inputs=["4\n1 1 1 1", "1\n-7\n", "2\n1 2 3"]))
    bad_tests = SUM_TESTS + [{"input": "1\n9\n", "expected_output": "10"}]
    body = _analyze(api_client, text="Read n and then n integers; print their sum.", question_type="code_write",
                    code_language="python", correct_answer=SUM_SOLUTION, test_cases=bad_tests).json()
    check = body["code_check"]
    assert (check["passed"], check["total"]) == (2, 3)
    assert check["results"][2]["actual_output"] == "9" and check["results"][2]["passed"] is False
    assert [(t["input"], t["expected_output"]) for t in body["suggested_test_cases"]] == [
        ("4\n1 1 1 1\n", "4"), ("1\n-7\n", "-7"), ("2\n1 2 3\n", "3")]


def test_unsafe_reference_solution_is_reported_not_run(api_client, monkeypatch):
    _graph(api_client)
    _fake_client(monkeypatch, error=RuntimeError("offline"))
    body = _analyze(api_client, text="Write a program.", question_type="code_write",
                    correct_answer="import os\nprint(os.listdir('.'))", test_cases=[{"input": "", "expected_output": "x"}]).json()
    assert body["code_check"]["passed"] == 0 and body["code_check"]["results"][0]["error"]


def test_manual_question_saved_with_origin(api_client):
    question = {"id": "m1", "text": "Read a word and print it reversed.", "question_type": "code_write", "marks": 6,
                "bloom_level": 3, "topic_ids": ["arrays"], "code_language": "python",
                "correct_answer": "print(input()[::-1])", "test_cases": [{"input": "abc\n", "expected_output": "cba"}],
                "scenario_based": True, "origin": "manual"}
    assert api_client.post(f"/api/v1/questions?subject_id={api_client.subject_id}", json=question).status_code == 200
    [saved] = api_client.get(f"/api/v1/questions?subject_id={api_client.subject_id}").json()
    assert saved["origin"] == "manual" and saved["scenario_based"] is True and saved["question_type"] == "code_write"


# ---------- code_write grading & exams ----------


def _code_write(**overrides) -> Question:
    fields = dict(id="cw", text="Sum the first n numbers.", question_type=CW, marks=6, bloom_level=BloomLevel.APPLY,
                  code_language="python", correct_answer=SUM_SOLUTION,
                  test_cases=[CodeTestCase(**t) for t in SUM_TESTS])
    fields.update(overrides)
    return Question(**fields)


def test_code_write_is_auto_graded_by_test_cases():
    assert CW in AUTO_GRADABLE_TYPES
    question = _code_write()
    full = grade_answer(question, SUM_SOLUTION)
    assert full.correct and full.marks_awarded == 6 and full.detail == "2/2 test cases passed"
    half = grade_answer(question, "input()\nprint(6)")
    assert not half.correct and half.marks_awarded == 3
    assert question.effective_skill_category.value == "coding"


def test_code_write_in_a_student_exam(api_client, clock):
    seed(api_client, [Question(**{**_code_write().model_dump(), "topic_ids": ["arrays"], "difficulty_score": 5.0})])
    exam_id = make_exam(api_client, ["cw"], go_live=T0 - timedelta(minutes=1), duration=30)
    start = api_client.post(f"/api/v1/exams/{exam_id}/start", headers={"Authorization": ""},
                            json={"student_name": "Asha", "student_identifier": "R1"}).json()
    public = start["exam"]["questions"][0]
    assert public["question_type"] == "code_write" and "test_cases" not in public and "correct_answer" not in public
    receipt = api_client.post(f"/api/v1/exams/{exam_id}/submit", headers={"Authorization": ""}, json={
        "student_name": "Asha", "attempt_id": start["attempt"]["attempt_id"],
        "answers": [{"question_id": "cw", "answer": SUM_SOLUTION}]}).json()
    assert receipt["auto_graded_marks"] == 6 and receipt["answers"][0]["status"] == "auto_graded"
    [sub] = api_client.get(f"/api/v1/exams/{exam_id}/submissions").json()
    assert sub["answers"][0]["test_cases_passed"] == 2 and sub["answers"][0]["skill_category"] == "coding"


def test_patterns_and_presets_accept_code_write(api_client):
    presets = api_client.get("/api/v1/patterns/presets").json()
    assert any("code_write" in s["question_types"] for p in presets for s in p["sections"])


# ---------- generation ----------


@pytest.fixture
def fake_generation(api_client, monkeypatch):
    from app.services import question_generation as gen

    seed_graph(api_client, {"queues": "Queues"})
    monkeypatch.setattr(gen, "query_similar_chunks", lambda *a, **k: [])
    prompts: list[str] = []

    def install(drafts):
        def generate_content(**kw):
            prompts.append(kw["contents"])
            return SimpleNamespace(parsed=QuestionDraftBatch(questions=drafts))

        monkeypatch.setattr(gen, "get_genai_client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))

    return install, prompts


def _draft(solution=SUM_SOLUTION, tests=SUM_TESTS):
    return GeneratedQuestionDraft(
        text="A delivery app batches n orders and needs the total parcel weight...", question_type="code_write",
        bloom_level="APPLY", marks=8, code_language="python", correct_answer=solution,
        test_cases=[CodeTestCase(**t) for t in tests], topic_names=["Queues"])


def test_generate_scenario_code_write(api_client, fake_generation):
    install, prompts = fake_generation
    install([_draft()])
    r = api_client.post("/api/v1/questions/generate", json={
        "subject_id": api_client.subject_id, "topic": "Queues", "num_questions": 1, "bloom_level": 3, "marks": 8,
        "question_type": "code_write", "scenario_based": True, "check_duplicates": False})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    question = result["question"]
    assert question["question_type"] == "code_write" and question["scenario_based"] is True
    assert question["origin"] == "generated" and question["topic_ids"] == ["queues"]
    assert "interview / industry scenario" in prompts[0] and "Input format" in prompts[0]


def test_plain_code_write_has_no_scenario_instruction(api_client, fake_generation):
    install, prompts = fake_generation
    install([_draft()])
    r = api_client.post("/api/v1/questions/generate", json={
        "subject_id": api_client.subject_id, "topic": "Queues", "num_questions": 1, "question_type": "code_write",
        "check_duplicates": False})
    assert r.json()["results"][0]["question"]["scenario_based"] is False
    assert "interview / industry scenario" not in prompts[0]


def test_rejected_draft_reason_is_fed_back_into_the_retry(api_client, fake_generation, monkeypatch):
    from app.services import question_generation as gen

    seed_graph(api_client, {"queues": "Queues"})
    monkeypatch.setattr(gen, "query_similar_chunks", lambda *a, **k: [])
    sys_solution = "import sys\nprint(sum(map(int, sys.stdin.read().split()[1:])))"
    replies = iter([[_draft(solution=sys_solution)], [_draft()]])
    prompts: list[str] = []

    def generate_content(**kw):
        prompts.append(kw["contents"])
        return SimpleNamespace(parsed=QuestionDraftBatch(questions=next(replies)))

    monkeypatch.setattr(gen, "get_genai_client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    r = api_client.post("/api/v1/questions/generate", json={
        "subject_id": api_client.subject_id, "topic": "Queues", "num_questions": 1, "question_type": "code_write",
        "check_duplicates": False})
    assert len(r.json()["results"]) == 1 and len(prompts) == 2
    assert "PREVIOUS ATTEMPT REJECTED" not in prompts[0]
    assert "PREVIOUS ATTEMPT REJECTED" in prompts[1] and "Import not allowed: sys" in prompts[1]
    assert "never `sys.stdin`" in prompts[0]  # the sandbox rules are in every coding prompt


def test_expected_outputs_come_from_running_the_reference(api_client, fake_generation):
    install, _ = fake_generation
    # The model mis-computed the second expected output; the solution is right.
    install([_draft(tests=[{"input": "3\n1 2 3\n", "expected_output": "6"}, {"input": "2\n-1 5\n", "expected_output": "5"}])])
    r = api_client.post("/api/v1/questions/generate", json={
        "subject_id": api_client.subject_id, "topic": "Queues", "num_questions": 1, "question_type": "code_write",
        "check_duplicates": False})
    [result] = r.json()["results"]
    assert [t["expected_output"] for t in result["question"]["test_cases"]] == ["6", "4"]


def test_generated_code_write_with_wrong_reference_is_dropped(api_client, fake_generation):
    install, prompts = fake_generation
    install([_draft(tests=[{"input": "1\n5\n", "expected_output": "999"}])])
    r = api_client.post("/api/v1/questions/generate", json={
        "subject_id": api_client.subject_id, "topic": "Queues", "num_questions": 1, "question_type": "code_write",
        "check_duplicates": False})
    assert r.json()["results"] == []
    assert len(prompts) == 3  # coding types retry before giving up


# ---------- PDF export ----------


def test_pdf_export_handles_code_write(api_client, clock):
    import io

    from pypdf import PdfReader

    seed(api_client, [Question(**{**_code_write().model_dump(), "topic_ids": ["arrays"], "difficulty_score": 5.0})])
    exam_id = make_exam(api_client, ["cw"], go_live=T0 + timedelta(days=1), duration=30)

    def text(kind):
        r = api_client.get(f"/api/v1/exams/{exam_id}/export/{kind}")
        assert r.status_code == 200, r.text
        return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)

    paper, key = text("paper"), text("answer-key")
    assert "write a complete program" in paper and "Sum the first n numbers." in paper
    assert "sum(nums[:n])" not in paper  # no solution on the question paper
    assert "Reference solution" in key and "sum(nums[:n])" in key
