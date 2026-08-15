import pickle
import re
from functools import lru_cache
from pathlib import Path

import networkx as nx

from app.core.config import get_settings


def normalize_topic_name(name: str) -> str:
    """Collapse a topic name to a stable node id (lowercase, single-spaced, alnum)."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


class KnowledgeGraphStore:
    """Thin wrapper around a NetworkX DiGraph used as the knowledge graph backend.

    Falls back to an in-memory/pickled graph when Neo4j is not configured
    (see app.core.config.Settings.neo4j_uri).
    """

    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.graph: nx.DiGraph = self._load()

    def _load(self) -> nx.DiGraph:
        if self.persist_path.exists():
            with open(self.persist_path, "rb") as f:
                return pickle.load(f)
        return nx.DiGraph()

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "wb") as f:
            pickle.dump(self.graph, f)

    def add_topic(self, topic_id: str, **attrs) -> None:
        self.graph.add_node(topic_id, **attrs)

    def add_relation(self, source_id: str, target_id: str, relation_type: str) -> None:
        self.graph.add_edge(source_id, target_id, relation_type=relation_type)

    def compute_pagerank(self) -> dict[str, float]:
        return nx.pagerank(self.graph) if self.graph.number_of_nodes() else {}


def get_neo4j_driver():
    """Return a Neo4j driver if credentials are configured, else None."""
    settings = get_settings()
    if not settings.neo4j_uri:
        return None
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


@lru_cache
def get_graph_store() -> KnowledgeGraphStore:
    settings = get_settings()
    return KnowledgeGraphStore(settings.graph_store_path)
