"""Removes a deleted document's contribution to the knowledge graph.
Questions already generated from that document's topics are deliberately
left untouched — they remain valid standalone content even after their
source material is gone."""

from app.core.graph_store import KnowledgeGraphStore


def _sources(data: dict) -> list[str]:
    if "source_documents" in data:
        return list(data["source_documents"])
    if data.get("source_document"):
        return [data["source_document"]]
    return []


def remove_document_from_graph(graph_store: KnowledgeGraphStore, filename: str) -> dict:
    """Drop `filename` from every node/edge's source list. A node/edge whose
    only supporting document was `filename` is removed entirely; one still
    supported by another document is kept, just with this filename dropped
    from its source list."""
    graph = graph_store.graph

    nodes_removed = 0
    for node_id in list(graph.nodes):
        sources = _sources(graph.nodes[node_id])
        if filename not in sources:
            continue
        remaining = [s for s in sources if s != filename]
        if remaining:
            graph.nodes[node_id]["source_documents"] = remaining
            graph.nodes[node_id].pop("source_document", None)
        else:
            graph.remove_node(node_id)  # also drops every edge touching it
            nodes_removed += 1

    edges_removed = 0
    for u, v in list(graph.edges):
        if not graph.has_node(u) or not graph.has_node(v):
            continue
        sources = _sources(graph.edges[u, v])
        if filename not in sources:
            continue
        remaining = [s for s in sources if s != filename]
        if remaining:
            graph.edges[u, v]["source_documents"] = remaining
        else:
            graph.remove_edge(u, v)
            edges_removed += 1

    return {"nodes_removed": nodes_removed, "edges_removed": edges_removed}
