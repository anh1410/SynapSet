from functools import lru_cache

from sentence_transformers import SentenceTransformer, util

from app.schemas.duplicate import DuplicateMatch
from app.schemas.question import Question

SEMANTIC_WEIGHT = 0.5
GRAPH_WEIGHT = 0.3
STRUCTURAL_WEIGHT = 0.2
DUPLICATE_THRESHOLD = 0.75


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    """Local sentence-embedding model — no API calls, no rate limits."""
    return SentenceTransformer("all-MiniLM-L6-v2")


def graph_overlap(topic_ids_a: list[str], topic_ids_b: list[str]) -> float:
    """Jaccard similarity over the sets of knowledge-graph topics each question is tagged with."""
    set_a, set_b = set(topic_ids_a), set(topic_ids_b)
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def structural_similarity(question_a: Question, question_b: Question) -> float:
    """Bloom level, question type, and marks match — a proxy for answer-shape similarity."""
    score = 0.0
    if question_a.bloom_level == question_b.bloom_level:
        score += 0.5
    if question_a.question_type == question_b.question_type:
        score += 0.3
    if question_a.marks == question_b.marks:
        score += 0.2
    return score


def find_duplicates(
    candidate: Question,
    existing_questions: list[Question],
    threshold: float = DUPLICATE_THRESHOLD,
) -> list[DuplicateMatch]:
    """Score `candidate` against every question in `existing_questions` using a weighted
    fusion of semantic similarity, knowledge-graph topic overlap, and structural similarity.
    Returns matches at or above `threshold`, sorted by final_score descending.
    """
    if not existing_questions:
        return []

    model = get_embedding_model()
    texts = [candidate.text] + [q.text for q in existing_questions]
    embeddings = model.encode(texts, convert_to_tensor=True)
    candidate_embedding = embeddings[0]

    matches: list[DuplicateMatch] = []
    for i, existing in enumerate(existing_questions, start=1):
        semantic = max(0.0, float(util.cos_sim(candidate_embedding, embeddings[i]).item()))
        graph = graph_overlap(candidate.topic_ids, existing.topic_ids)
        structural = structural_similarity(candidate, existing)
        final = SEMANTIC_WEIGHT * semantic + GRAPH_WEIGHT * graph + STRUCTURAL_WEIGHT * structural

        match = DuplicateMatch(
            existing_question_id=existing.id,
            semantic_score=round(semantic, 4),
            graph_score=round(graph, 4),
            structural_score=round(structural, 4),
            final_score=round(final, 4),
            is_duplicate=final >= threshold,
        )
        if match.final_score >= threshold:
            matches.append(match)

    return sorted(matches, key=lambda m: -m.final_score)
