"""Merges near-duplicate topic nodes created by ingesting overlapping material
multiple times (e.g. "Public Cloud" extracted once, "Public Clouds" extracted
again from a different chunk/document). Deliberately conservative: it only
merges nodes whose normalized ids differ by a trailing "s" (simple singular/
plural variants), which is what's actually been observed in practice, rather
than a fuzzy similarity threshold that risks merging genuinely distinct topics.
"""

from app.core.graph_store import KnowledgeGraphStore
from app.core.question_bank import QuestionBank


def _singularize(node_id: str) -> str:
    return node_id[:-1] if node_id.endswith("s") and not node_id.endswith("ss") else node_id


def find_duplicate_groups(graph_store: KnowledgeGraphStore) -> list[list[str]]:
    """Group node ids that share the same singularized form. Only groups of 2+ are duplicates."""
    groups: dict[str, list[str]] = {}
    for node_id in graph_store.graph.nodes:
        key = _singularize(node_id)
        groups.setdefault(key, []).append(node_id)
    return [ids for ids in groups.values() if len(ids) > 1]


def merge_duplicate_topics(graph_store: KnowledgeGraphStore, bank: QuestionBank) -> dict:
    """Merge each duplicate group into a single canonical node, redirect edges,
    remap question topic_ids, recompute PageRank, and persist both stores."""
    graph = graph_store.graph
    groups = find_duplicate_groups(graph_store)

    merges: dict[str, str] = {}  # old_id -> canonical_id
    for ids in groups:
        canonical = max(ids, key=lambda n: (graph.nodes[n].get("importance_score", 0.0), graph.degree(n)))
        for other in ids:
            if other != canonical:
                merges[other] = canonical

    if not merges:
        return {"merged_groups": 0, "nodes_removed": 0, "questions_updated": 0}

    for old_id, canonical in merges.items():
        for pred in list(graph.predecessors(old_id)):
            if pred != canonical and not graph.has_edge(pred, canonical):
                graph.add_edge(pred, canonical, **graph.edges[pred, old_id])
        for succ in list(graph.successors(old_id)):
            if succ != canonical and not graph.has_edge(canonical, succ):
                graph.add_edge(canonical, succ, **graph.edges[old_id, succ])
        graph.remove_node(old_id)

    questions_updated = 0
    for question in bank.list():
        if not any(tid in merges for tid in question.topic_ids):
            continue
        seen: list[str] = []
        for tid in question.topic_ids:
            mapped = merges.get(tid, tid)
            if mapped not in seen:
                seen.append(mapped)
        question.topic_ids = seen
        bank.add(question)
        questions_updated += 1

    scores = graph_store.compute_pagerank()
    for node_id, score in scores.items():
        graph.nodes[node_id]["importance_score"] = score
    graph_store.save()

    return {
        "merged_groups": len(groups),
        "nodes_removed": len(merges),
        "questions_updated": questions_updated,
    }
