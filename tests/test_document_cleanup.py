from app.core.graph_store import KnowledgeGraphStore
from app.services.document_cleanup import remove_document_from_graph


def test_topic_only_in_deleted_document_is_removed(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("virtualization", name="Virtualization", source_documents=["notes.pdf"])

    result = remove_document_from_graph(gs, "notes.pdf")

    assert result == {"nodes_removed": 1, "edges_removed": 0}
    assert "virtualization" not in gs.graph.nodes


def test_topic_supported_by_another_document_survives(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("virtualization", name="Virtualization", source_documents=["notes.pdf", "slides.pptx"])

    result = remove_document_from_graph(gs, "notes.pdf")

    assert result == {"nodes_removed": 0, "edges_removed": 0}
    assert "virtualization" in gs.graph.nodes
    assert gs.graph.nodes["virtualization"]["source_documents"] == ["slides.pptx"]


def test_old_style_singular_source_document_field_is_handled(tmp_path):
    # Nodes created before source_documents (plural) existed only have the
    # old singular field - cleanup must still work for them.
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("hypervisor", name="Hypervisor", source_document="old_notes.pdf")

    result = remove_document_from_graph(gs, "old_notes.pdf")

    assert result == {"nodes_removed": 1, "edges_removed": 0}
    assert "hypervisor" not in gs.graph.nodes


def test_edge_only_supported_by_deleted_document_is_removed(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("hypervisor", name="Hypervisor", source_documents=["notes.pdf", "slides.pptx"])
    gs.add_topic("virtualization", name="Virtualization", source_documents=["notes.pdf", "slides.pptx"])
    gs.add_relation("hypervisor", "virtualization", "PREREQUISITE_OF", source_document="notes.pdf")

    result = remove_document_from_graph(gs, "notes.pdf")

    # both nodes survive (still supported by slides.pptx), edge is dropped
    assert result == {"nodes_removed": 0, "edges_removed": 1}
    assert "hypervisor" in gs.graph.nodes
    assert "virtualization" in gs.graph.nodes
    assert not gs.graph.has_edge("hypervisor", "virtualization")


def test_edge_supported_by_another_document_survives(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("hypervisor", name="Hypervisor", source_documents=["notes.pdf", "slides.pptx"])
    gs.add_topic("virtualization", name="Virtualization", source_documents=["notes.pdf", "slides.pptx"])
    gs.add_relation("hypervisor", "virtualization", "PREREQUISITE_OF", source_document="notes.pdf")
    gs.add_relation("hypervisor", "virtualization", "PREREQUISITE_OF", source_document="slides.pptx")

    result = remove_document_from_graph(gs, "notes.pdf")

    assert result == {"nodes_removed": 0, "edges_removed": 0}
    assert gs.graph.has_edge("hypervisor", "virtualization")
    assert gs.graph.edges["hypervisor", "virtualization"]["source_documents"] == ["slides.pptx"]


def test_deleting_unrelated_document_is_a_noop(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("virtualization", name="Virtualization", source_documents=["notes.pdf"])

    result = remove_document_from_graph(gs, "unrelated.pdf")

    assert result == {"nodes_removed": 0, "edges_removed": 0}
    assert "virtualization" in gs.graph.nodes
