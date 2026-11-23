"""LLM evals for SynapSet's retrieval-grounded question generation.

The real pipeline is exercised end to end: golden syllabus text -> Gemini embeddings -> Chroma
retrieval -> Gemini generation. Output quality is then scored with DeepEval, using Gemini as the
judge. Needs GOOGLE_API_KEY and uses API quota.

Metrics per generated question:
  relevance      (GEval)               is it about the requested topic and a real, answerable exam question?
  faithfulness   (FaithfulnessMetric)  is every claim in it supported by the retrieved syllabus text?
  hallucination  (HallucinationMetric) does it contradict the source syllabus? (1.0 = no contradictions)
All three score 0-1 where higher is better, and each threshold is the minimum passing score.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import FaithfulnessMetric, GEval, HallucinationMetric
from deepeval.test_case import SingleTurnParams

from app.core.config import get_settings
from app.core.graph_store import KnowledgeGraphStore, normalize_topic_name
from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from app.services.document_extraction import TextChunk
from app.services.question_generation import generate_questions
from app.services.vector_indexing import index_chunks, query_similar_chunks
from evals.dataset import GoldenCase, render_question
from evals.judge import DEFAULT_JUDGE_MODEL

EVAL_SUBJECT = "eval-subject"
RETRIEVAL_TOP_K = 5
RESULTS_PATH = Path(__file__).parent / "results" / "latest.json"

# Minimum passing score per metric. Hallucination is checked against one context, so it is effectively 0 or 1.
THRESHOLDS = {"relevance": 0.7, "faithfulness": 0.7, "hallucination": 0.5}
PASS_RATE_GATE = 0.8  # share of cases that must pass each metric
RECALL_GATE = 0.9  # share of cases whose own syllabus must appear in the top-k retrieved chunks

RELEVANCE_CRITERIA = (
    "The input asks for an exam question on a specific topic. Judge whether the question and its model "
    "answer are directly about that topic rather than a tangential one, and whether the question reads "
    "like a real exam question: clear, answerable, and asking for one well-defined task. Multiple-choice "
    "options are intentionally left out of the output, so do not penalize their absence."
)


class EvalWorkspace:
    """All golden syllabi indexed and graphed once, with generation and retrieval memoized per case."""

    def __init__(self, cases: list[GoldenCase], graph_store: KnowledgeGraphStore):
        self.cases = cases
        self.graph_store = graph_store
        self._retrieved: dict[str, list[dict]] = {}
        self._generated: dict[str, Question | None] = {}

    @classmethod
    def build(cls, cases: list[GoldenCase], graph_store: KnowledgeGraphStore) -> "EvalWorkspace":
        chunks = [TextChunk(text=c.syllabus, chunk_index=0, source_document=c.source_document) for c in cases]
        index_chunks(chunks, EVAL_SUBJECT)
        _populate_graph(graph_store, cases)
        return cls(cases, graph_store)

    def retrieved(self, case: GoldenCase) -> list[dict]:
        if case.id not in self._retrieved:
            self._retrieved[case.id] = query_similar_chunks(case.topic, EVAL_SUBJECT, n_results=RETRIEVAL_TOP_K)
        return self._retrieved[case.id]

    def generated(self, case: GoldenCase) -> Question | None:
        if case.id not in self._generated:
            questions = generate_questions(
                topic=case.topic,
                graph_store=self.graph_store,
                subject_id=EVAL_SUBJECT,
                num_questions=1,
                bloom_level=BloomLevel[case.bloom_level],
                marks=case.marks,
                question_type=QuestionType(case.question_type),
            )
            self._generated[case.id] = questions[0] if questions else None
        return self._generated[case.id]


def _populate_graph(graph_store: KnowledgeGraphStore, cases: list[GoldenCase]) -> None:
    node_ids = {normalize_topic_name(c.topic): c.topic for c in cases}
    for node_id, name in node_ids.items():
        graph_store.add_topic(node_id, name=name)
    for case in cases:
        for prerequisite in case.prerequisites:
            prerequisite_id = normalize_topic_name(prerequisite)
            if prerequisite_id in node_ids:
                graph_store.add_relation(prerequisite_id, normalize_topic_name(case.topic), "PREREQUISITE_OF")


def build_metrics(judge) -> dict:
    return {
        "relevance": GEval(
            name="Topic Relevance",
            criteria=RELEVANCE_CRITERIA,
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
            threshold=THRESHOLDS["relevance"],
            model=judge,
            async_mode=False,
        ),
        "faithfulness": FaithfulnessMetric(
            threshold=THRESHOLDS["faithfulness"], model=judge, include_reason=True, async_mode=False
        ),
        "hallucination": HallucinationMetric(
            threshold=THRESHOLDS["hallucination"], model=judge, include_reason=True, async_mode=False
        ),
    }


def result_row(case: GoldenCase, question: Question | None, metrics: dict, error: str | None = None) -> dict:
    return {
        "case_id": case.id,
        "topic": case.topic,
        "bloom_level": case.bloom_level,
        "question_type": case.question_type,
        "question": render_question(question) if question else None,
        "error": error,
        "scores": {name: None if m.score is None else round(m.score, 3) for name, m in metrics.items()},
        "passed": {name: bool(m.success) for name, m in metrics.items()},
        "reasons": {name: getattr(m, "reason", None) for name, m in metrics.items()},
    }


def summarize(rows: list[dict]) -> dict:
    """Per-metric stats. A case whose metric errored (no score) counts as a failure, not as missing."""
    summary = {}
    for name in THRESHOLDS:
        scored = [r["scores"][name] for r in rows if r["scores"].get(name) is not None]
        summary[name] = {
            "cases": len(rows),
            "errors": len(rows) - len(scored),
            "mean_score": round(sum(scored) / len(scored), 3) if scored else None,
            "pass_rate": round(sum(r["passed"][name] for r in rows) / len(rows), 3) if rows else None,
        }
    return summary


def write_results(rows: list[dict]) -> Path:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generation_model": get_settings().generation_model,
        "judge_model": os.environ.get("EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
        "thresholds": THRESHOLDS,
        "summary": summarize(rows),
        "cases": rows,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return RESULTS_PATH
