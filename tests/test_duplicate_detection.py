from app.schemas.bloom import BloomLevel
from app.schemas.question import Question, QuestionType
from app.services.duplicate_detection import find_duplicates, graph_overlap, structural_similarity


def test_graph_overlap():
    assert graph_overlap([], []) == 0.0
    assert graph_overlap(["a", "b"], ["a", "b"]) == 1.0
    assert graph_overlap(["a", "b"], ["b", "c"]) == 1 / 3
    assert graph_overlap(["a"], []) == 0.0


def test_structural_similarity_identical():
    q1 = Question(id="1", text="a", question_type=QuestionType.MCQ, marks=5, bloom_level=BloomLevel.UNDERSTAND)
    q2 = Question(id="2", text="b", question_type=QuestionType.MCQ, marks=5, bloom_level=BloomLevel.UNDERSTAND)
    assert structural_similarity(q1, q2) == 1.0


def test_structural_similarity_all_different():
    q1 = Question(id="1", text="a", question_type=QuestionType.MCQ, marks=5, bloom_level=BloomLevel.UNDERSTAND)
    q2 = Question(id="2", text="b", question_type=QuestionType.LONG_ANSWER, marks=10, bloom_level=BloomLevel.CREATE)
    assert structural_similarity(q1, q2) == 0.0


def test_find_duplicates_flags_reworded_question(sample_questions):
    candidate = Question(
        id="candidate",
        text="Describe what virtualization is and its role in cloud computing.",
        question_type=QuestionType.SHORT_ANSWER,
        marks=5,
        bloom_level=BloomLevel.UNDERSTAND,
        topic_ids=["virtualization", "cloud_architecture"],
    )
    matches = find_duplicates(candidate, sample_questions, threshold=0.0)
    assert len(matches) == len(sample_questions)

    best = max(matches, key=lambda m: m.final_score)
    assert best.existing_question_id == "q1"
    assert best.is_duplicate


def test_find_duplicates_empty_pool():
    q = Question(id="1", text="a", question_type=QuestionType.MCQ, marks=1, bloom_level=BloomLevel.REMEMBER)
    assert find_duplicates(q, []) == []
