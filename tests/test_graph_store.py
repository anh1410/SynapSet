from app.core.graph_store import KnowledgeGraphStore, normalize_topic_name


def test_normalize_topic_name():
    assert normalize_topic_name("Parallel Computing") == "parallel_computing"
    assert normalize_topic_name("  IaaS (Infrastructure) ") == "iaas_infrastructure"
    assert normalize_topic_name("A---B") == "a_b"


def test_graph_store_add_and_pagerank(graph_store):
    assert graph_store.graph.number_of_nodes() == 4
    assert graph_store.graph.number_of_edges() == 3

    scores = graph_store.compute_pagerank()
    assert set(scores.keys()) == set(graph_store.graph.nodes)
    assert all(0 <= v <= 1 for v in scores.values())


def test_graph_store_persists(tmp_path):
    path = tmp_path / "g.gpickle"
    gs = KnowledgeGraphStore(str(path))
    gs.add_topic("a", name="A")
    gs.save()

    reloaded = KnowledgeGraphStore(str(path))
    assert reloaded.graph.has_node("a")


def test_graph_store_empty_pagerank(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "empty.gpickle"))
    assert gs.compute_pagerank() == {}
