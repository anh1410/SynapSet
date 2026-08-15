from app.core.graph_store import KnowledgeGraphStore
from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from app.services.difficulty_scoring import extract_features, heuristic_difficulty, score_difficulty


def test_extract_features_no_topics(graph_store):
    q = Question(id="1", text="a b c", question_type=QuestionType.MCQ, marks=1, bloom_level=BloomLevel.REMEMBER)
    features = extract_features(q, graph_store)
    assert features["num_topics"] == 0.0
    assert features["avg_prerequisite_depth"] == 0.0


def test_extract_features_with_topics(graph_store):
    # graph_store fixture: hypervisor -> virtualization -> iaas, so iaas has prereq depth 2
    q = Question(
        id="1",
        text="a b c",
        question_type=QuestionType.SHORT_ANSWER,
        marks=5,
        bloom_level=BloomLevel.UNDERSTAND,
        topic_ids=["iaas"],
    )
    features = extract_features(q, graph_store)
    assert features["avg_prerequisite_depth"] == 2.0
    assert features["max_prerequisite_count"] == 1.0


def test_heuristic_difficulty_monotonic_in_bloom():
    base = {
        "bloom_level": 1.0,
        "avg_prerequisite_depth": 0.0,
        "max_prerequisite_count": 0.0,
        "marks": 1.0,
        "text_length": 10.0,
    }
    low = heuristic_difficulty(base)
    high = heuristic_difficulty({**base, "bloom_level": 6.0})
    assert high > low


def test_heuristic_difficulty_clamped_to_range():
    huge = {
        "bloom_level": 6.0,
        "avg_prerequisite_depth": 100.0,
        "max_prerequisite_count": 100.0,
        "marks": 100.0,
        "text_length": 1000.0,
    }
    assert heuristic_difficulty(huge) == 10.0


def test_score_difficulty_returns_valid_range(graph_store, sample_questions):
    ds = score_difficulty(sample_questions[0], graph_store)
    assert 1.0 <= ds.score <= 10.0
    assert ds.method == "model"
    assert set(ds.shap_contributions.keys()) == set(ds.features.keys())


def test_extract_features_handles_cyclic_prerequisite_graph(tmp_path):
    # LLM extraction isn't guaranteed to produce a DAG (e.g. A prereq-of B
    # from one chunk, B prereq-of A from another) - must not crash.
    gs = KnowledgeGraphStore(str(tmp_path / "cyclic.gpickle"))
    gs.add_topic("a", name="A")
    gs.add_topic("b", name="B")
    gs.add_relation("a", "b", "PREREQUISITE_OF")
    gs.add_relation("b", "a", "PREREQUISITE_OF")

    q = Question(
        id="1", text="a b c", question_type=QuestionType.MCQ, marks=1,
        bloom_level=BloomLevel.REMEMBER, topic_ids=["a"],
    )
    features = extract_features(q, gs)
    assert features["avg_prerequisite_depth"] == 0.0
