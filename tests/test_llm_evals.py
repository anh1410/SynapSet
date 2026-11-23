"""LLM-judged evals of SynapSet's question generation against a golden dataset of syllabus inputs.

Calls the real Gemini API for embeddings, generation, and judging, so it is excluded from the default
run. Run it with:

    pytest -m eval                          # all golden cases
    EVAL_CASE_LIMIT=5 pytest -m eval        # quick pass over the first 5 cases

Each case costs ~10 Gemini requests (generation, embedding, and ~8 judge calls). Free-tier keys allow only
~20 requests/day per model, so use EVAL_CASE_LIMIT there, or set EVAL_JUDGE_MODEL to a model with more quota.
Per-run scores are written to evals/results/latest.json.
"""

import pytest

from evals.dataset import load_golden_dataset, structural_problems

pytestmark = pytest.mark.eval

CASES = load_golden_dataset()

# DeepEval and the harness are imported inside fixtures/tests so the default run never pays their import cost.


def _clear_caches() -> None:
    from app.core.config import get_settings
    from app.core.vector_store import get_chroma_client

    get_settings.cache_clear()
    get_chroma_client.cache_clear()


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    pytest.importorskip("deepeval")
    from app.core.config import get_settings
    from app.core.graph_store import KnowledgeGraphStore

    root = tmp_path_factory.mktemp("evals")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(root / "chroma"))
    _clear_caches()
    try:
        if not get_settings().google_api_key:
            pytest.skip("GOOGLE_API_KEY is not set; evals call the real Gemini API")
        from evals.harness import EvalWorkspace

        yield EvalWorkspace.build(CASES, KnowledgeGraphStore(str(root / "graph.gpickle")))
    finally:
        monkeypatch.undo()
        _clear_caches()


@pytest.fixture(scope="module")
def judge():
    from evals.judge import GeminiJudge

    judge = GeminiJudge()
    try:
        judge.preflight()
    except Exception as exc:
        pytest.fail(
            f"judge model '{judge.get_model_name()}' is unreachable ({type(exc).__name__}); "
            "set EVAL_JUDGE_MODEL to a model your API key can use",
            pytrace=False,
        )
    return judge


@pytest.fixture(scope="module")
def results():
    rows: list[dict] = []
    yield rows
    if rows:
        from evals.harness import write_results

        write_results(rows)


def test_retrieval_recall_at_k(workspace):
    from evals.harness import RECALL_GATE, RETRIEVAL_TOP_K

    misses = [
        case.id
        for case in CASES
        if case.source_document not in [h["metadata"]["source_document"] for h in workspace.retrieved(case)]
    ]
    recall = 1 - len(misses) / len(CASES)
    assert recall >= RECALL_GATE, f"recall@{RETRIEVAL_TOP_K} was {recall:.2f}; own syllabus not retrieved for {misses}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_generated_question_is_well_formed(case, workspace):
    question = workspace.generated(case)
    assert question is not None, "generator returned no question"
    problems = structural_problems(case, question)
    assert not problems, "; ".join(problems)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_generation_quality(case, workspace, judge, results):
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase
    from evals.dataset import render_question
    from evals.harness import build_metrics, result_row

    question = workspace.generated(case)
    assert question is not None, "generator returned no question"

    test_case = LLMTestCase(
        input=case.prompt,
        actual_output=render_question(question, include_options=False),
        retrieval_context=[hit["text"] for hit in workspace.retrieved(case)],
        context=[case.syllabus],
    )
    metrics = build_metrics(judge)
    error = None
    try:
        assert_test(test_case, list(metrics.values()), run_async=False)
    except AssertionError:
        raise  # a metric scored below its threshold; the scores are recorded below
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        results.append(result_row(case, question, metrics, error))


def test_aggregate_quality_gate(results):
    from evals.harness import PASS_RATE_GATE, summarize

    if not results:
        pytest.skip("no per-case results were collected in this run")
    below_gate = {
        name: stats
        for name, stats in summarize(results).items()
        if stats["pass_rate"] < PASS_RATE_GATE
    }
    assert not below_gate, f"pass rate below {PASS_RATE_GATE:.0%} for: {below_gate}"
