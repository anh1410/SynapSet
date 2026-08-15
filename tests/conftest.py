import pytest
from fastapi.testclient import TestClient

from app.core.graph_store import KnowledgeGraphStore
from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType


@pytest.fixture
def graph_store(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "graph.gpickle"))
    gs.add_topic("virtualization", name="Virtualization", description="")
    gs.add_topic("iaas", name="Infrastructure as a Service", description="")
    gs.add_topic("cloud_architecture", name="Cloud Architecture", description="")
    gs.add_topic("hypervisor", name="Hypervisor", description="")
    gs.add_relation("hypervisor", "virtualization", "PREREQUISITE_OF")
    gs.add_relation("virtualization", "iaas", "PREREQUISITE_OF")
    gs.add_relation("virtualization", "cloud_architecture", "PREREQUISITE_OF")
    scores = gs.compute_pagerank()
    for node_id, score in scores.items():
        gs.graph.nodes[node_id]["importance_score"] = score
    return gs


@pytest.fixture
def sample_questions():
    return [
        Question(
            id="q1",
            text="Define virtualization and its role in cloud computing.",
            question_type=QuestionType.SHORT_ANSWER,
            marks=5,
            bloom_level=BloomLevel.UNDERSTAND,
            topic_ids=["virtualization", "cloud_architecture"],
        ),
        Question(
            id="q2",
            text="What is a hypervisor and how does it enable virtualization?",
            question_type=QuestionType.SHORT_ANSWER,
            marks=5,
            bloom_level=BloomLevel.UNDERSTAND,
            topic_ids=["hypervisor", "virtualization"],
        ),
        Question(
            id="q3",
            text="List the deployment models of cloud computing.",
            question_type=QuestionType.MCQ,
            marks=1,
            bloom_level=BloomLevel.REMEMBER,
            topic_ids=["cloud_architecture"],
            options=["Public", "Private", "Hybrid", "Community"],
            correct_answer="Public",
        ),
    ]


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """A TestClient wired to isolated, per-test storage (graph/bank/chroma/uploads/exports)
    so API tests never touch real project data."""
    monkeypatch.setenv("GRAPH_STORE_PATH", str(tmp_path / "graph.gpickle"))
    monkeypatch.setenv("QUESTION_BANK_PATH", str(tmp_path / "bank.json"))
    monkeypatch.setenv("DOCUMENT_STORE_PATH", str(tmp_path / "documents.json"))
    monkeypatch.setenv("PAPER_STORE_PATH", str(tmp_path / "paper_blueprints.json"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))

    from app.core.config import get_settings
    from app.core.document_store import get_document_store
    from app.core.graph_store import get_graph_store
    from app.core.paper_store import get_paper_store
    from app.core.question_bank import get_question_bank
    from app.core.vector_store import get_chroma_client

    cached_fns = (
        get_settings,
        get_graph_store,
        get_question_bank,
        get_document_store,
        get_paper_store,
        get_chroma_client,
    )
    for cached in cached_fns:
        cached.cache_clear()

    from app.main import app

    with TestClient(app) as client:
        yield client

    for cached in cached_fns:
        cached.cache_clear()
