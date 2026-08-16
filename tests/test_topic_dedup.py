from app.core.graph_store import KnowledgeGraphStore
from app.core.question_bank import QuestionBank
from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from app.services.topic_dedup import find_duplicate_groups, merge_duplicate_topics


def _graph(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("public_cloud", name="Public Cloud", importance_score=0.05)
    gs.add_topic("public_clouds", name="Public Clouds", importance_score=0.09)
    gs.add_topic("hybrid_cloud", name="Hybrid Cloud", importance_score=0.03)
    gs.add_relation("public_cloud", "hybrid_cloud", "PREREQUISITE_OF")
    return gs


def test_find_duplicate_groups(tmp_path):
    gs = _graph(tmp_path)
    groups = find_duplicate_groups(gs)
    assert len(groups) == 1
    assert set(groups[0]) == {"public_cloud", "public_clouds"}


def test_find_duplicate_groups_no_false_positives(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("cloud_computing", name="Cloud Computing")
    gs.add_topic("cloud_computing_architecture", name="Cloud Computing Architecture")
    gs.add_topic("aws", name="AWS")
    assert find_duplicate_groups(gs) == []


def test_merge_duplicate_topics(tmp_path):
    gs = _graph(tmp_path)
    bank = QuestionBank(str(tmp_path / "bank.json"))
    bank.add(
        Question(
            id="q1", text="Describe public clouds", question_type=QuestionType.SHORT_ANSWER,
            marks=5, bloom_level=BloomLevel.UNDERSTAND, topic_ids=["public_cloud", "public_clouds"],
        )
    )

    result = merge_duplicate_topics(gs, bank)

    assert result == {"merged_groups": 1, "nodes_removed": 1, "questions_updated": 1}
    # higher importance_score (public_clouds, 0.09) wins as canonical
    assert set(gs.graph.nodes) == {"public_clouds", "hybrid_cloud"}
    assert gs.graph.has_edge("public_clouds", "hybrid_cloud")

    merged_question = bank.get("q1")
    assert merged_question.topic_ids == ["public_clouds"]


def test_merge_duplicate_topics_no_duplicates_is_noop(tmp_path):
    gs = KnowledgeGraphStore(str(tmp_path / "g.gpickle"))
    gs.add_topic("a", name="A")
    bank = QuestionBank(str(tmp_path / "bank.json"))
    result = merge_duplicate_topics(gs, bank)
    assert result == {"merged_groups": 0, "nodes_removed": 0, "questions_updated": 0}
