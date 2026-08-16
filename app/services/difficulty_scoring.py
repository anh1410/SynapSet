"""Explainable difficulty scoring.

NOTE ON TRAINING DATA: the roadmap calls for training on real per-question
classroom scores, which don't exist yet (no exam has been run through this
system). Until that data is collected, `get_default_model()` bootstraps an
XGBoost regressor on a synthetic dataset labeled by `heuristic_difficulty()`
-- a hand-weighted formula over graph/text features. This makes the
scorer + SHAP pipeline fully functional today, but the *scores themselves*
are only as good as the heuristic until real labels replace the synthetic
ones via `train_difficulty_model(real_features, real_labels)`.
"""

import random
from functools import lru_cache

import networkx as nx
import pandas as pd
import shap
import xgboost as xgb

from app.core.graph_store import KnowledgeGraphStore
from app.schemas.difficulty import DifficultyScore
from app.schemas.question import Question

FEATURE_NAMES = [
    "bloom_level",
    "marks",
    "text_length",
    "num_topics",
    "avg_prerequisite_depth",
    "max_prerequisite_count",
    "avg_importance_score",
]


def _prereq_subgraph(graph: nx.DiGraph) -> nx.DiGraph:
    edges = [(u, v) for u, v, d in graph.edges(data=True) if d.get("relation_type") == "PREREQUISITE_OF"]
    sub = nx.DiGraph()
    sub.add_nodes_from(graph.nodes(data=True))
    sub.add_edges_from(edges)
    return sub


def _topic_depth(node_id: str, prereq_graph: nx.DiGraph) -> int:
    """Length of the longest prerequisite chain leading up to this topic."""
    if node_id not in prereq_graph:
        return 0
    ancestors = nx.ancestors(prereq_graph, node_id)
    if not ancestors:
        return 0
    subgraph = prereq_graph.subgraph(ancestors | {node_id})
    try:
        return nx.dag_longest_path_length(subgraph)
    except nx.NetworkXUnfeasible:
        # LLM-extracted relations aren't guaranteed acyclic (e.g. A prereq-of B
        # from one chunk, B prereq-of A from another) — degrade gracefully.
        return 0


def extract_features(question: Question, graph_store: KnowledgeGraphStore) -> dict[str, float]:
    graph = graph_store.graph
    prereq_graph = _prereq_subgraph(graph)

    depths, prereq_counts, importances = [], [], []
    for topic_id in question.topic_ids:
        depths.append(_topic_depth(topic_id, prereq_graph))
        prereq_counts.append(prereq_graph.in_degree(topic_id) if topic_id in prereq_graph else 0)
        if topic_id in graph:
            importances.append(graph.nodes[topic_id].get("importance_score", 0.0))

    return {
        "bloom_level": float(question.bloom_level),
        "marks": float(question.marks),
        "text_length": float(len(question.text.split())),
        "num_topics": float(len(question.topic_ids)),
        "avg_prerequisite_depth": (sum(depths) / len(depths)) if depths else 0.0,
        "max_prerequisite_count": float(max(prereq_counts)) if prereq_counts else 0.0,
        "avg_importance_score": (sum(importances) / len(importances)) if importances else 0.0,
    }


def heuristic_difficulty(features: dict[str, float]) -> float:
    """Hand-weighted formula, used both as an instant fallback score and as
    the bootstrap training label until real classroom score data exists."""
    raw = (
        features["bloom_level"] * 1.0
        + features["avg_prerequisite_depth"] * 1.2
        + features["max_prerequisite_count"] * 0.5
        + features["marks"] * 0.3
        + features["text_length"] * 0.02
    )
    return max(1.0, min(10.0, raw))


def _generate_synthetic_dataset(n: int = 300, seed: int = 42) -> tuple[list[dict], list[float]]:
    rng = random.Random(seed)
    rows, labels = [], []
    for _ in range(n):
        features = {
            "bloom_level": float(rng.randint(1, 6)),
            "marks": float(rng.choice([1, 2, 5, 10])),
            "text_length": float(rng.randint(5, 60)),
            "num_topics": float(rng.randint(1, 4)),
            "avg_prerequisite_depth": float(rng.randint(0, 5)),
            "max_prerequisite_count": float(rng.randint(0, 6)),
            "avg_importance_score": rng.uniform(0, 0.2),
        }
        rows.append(features)
        labels.append(heuristic_difficulty(features))
    return rows, labels


def train_difficulty_model(
    training_rows: list[dict] | None = None, labels: list[float] | None = None
) -> xgb.XGBRegressor:
    if training_rows is None or labels is None:
        training_rows, labels = _generate_synthetic_dataset()
    X = pd.DataFrame(training_rows)[FEATURE_NAMES]
    model = xgb.XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42)
    model.fit(X, labels)
    return model


@lru_cache
def get_default_model() -> xgb.XGBRegressor:
    """Bootstrap model — see module docstring. Swap for a model trained on
    real per-question classroom scores once that data exists."""
    return train_difficulty_model()


def score_difficulty(
    question: Question, graph_store: KnowledgeGraphStore, model: xgb.XGBRegressor | None = None
) -> DifficultyScore:
    features = extract_features(question, graph_store)
    model = model or get_default_model()

    X = pd.DataFrame([features])[FEATURE_NAMES]
    prediction = max(1.0, min(10.0, float(model.predict(X)[0])))

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)[0]
    contributions = {name: round(float(val), 4) for name, val in zip(FEATURE_NAMES, shap_values)}

    return DifficultyScore(
        score=round(prediction, 2),
        features=features,
        shap_contributions=contributions,
        method="model",
    )
