"""Where a question came from: the material it was grounded on and its place
in the knowledge graph.

Questions generated since provenance recording carry exactly what the
generator saw (retrieved passages + graph relations). Older questions - or
ones written by hand - don't, so for those the closest indexed passages are
retrieved now and clearly labelled as reconstructed, never presented as what
the model actually used.
"""

from pydantic import BaseModel

from app.core.graph_store import KnowledgeGraphStore
from app.schemas.question import Question, SourceChunk
from app.schemas.skill import difficulty_bucket
from app.services.question_generation import chunks_from_hits
from app.services.vector_indexing import query_similar_chunks


class TopicContext(BaseModel):
    id: str
    name: str
    description: str
    importance_score: float | None
    prerequisites: list[str]  # topics that are PREREQUISITE_OF this one
    leads_to: list[str]  # topics this one is a prerequisite of
    course_outcomes: list[str]  # MAPS_TO targets


class Evidence(BaseModel):
    question_id: str
    recorded: bool  # True = captured at generation time; False = reconstructed now
    note: str
    requested_topic: str | None
    model: str | None
    generated_at: str | None
    chunks: list[SourceChunk]
    graph_relations: list[str]
    topics: list[TopicContext]
    bloom_level: int
    difficulty_score: float | None
    difficulty: str
    question_type: str
    skill_category: str
    co_ids: list[str]


def _topic_context(topic_id: str, graph_store: KnowledgeGraphStore) -> TopicContext | None:
    graph = graph_store.graph
    if topic_id not in graph:
        return None
    data = graph.nodes[topic_id]
    name = lambda n: graph.nodes[n].get("name", n)  # noqa: E731
    prereqs, leads, cos = [], [], []
    for pred in graph.predecessors(topic_id):
        if graph.edges[pred, topic_id].get("relation_type") == "PREREQUISITE_OF":
            prereqs.append(name(pred))
    for succ in graph.successors(topic_id):
        rel = graph.edges[topic_id, succ].get("relation_type")
        if rel == "PREREQUISITE_OF":
            leads.append(name(succ))
        elif rel == "MAPS_TO":
            cos.append(name(succ))
    return TopicContext(
        id=topic_id,
        name=data.get("name", topic_id),
        description=data.get("description", ""),
        importance_score=data.get("importance_score"),
        prerequisites=sorted(prereqs),
        leads_to=sorted(leads),
        course_outcomes=sorted(cos),
    )


def question_evidence(question: Question, graph_store: KnowledgeGraphStore, subject_id: str) -> Evidence:
    topics = [ctx for t in question.topic_ids if (ctx := _topic_context(t, graph_store)) is not None]
    p = question.provenance
    if p is not None:
        recorded, note = True, "Recorded when this question was generated: these are the passages and graph relations the model was given."
        chunks, relations = p.retrieved_chunks, p.graph_relations
        requested, model, generated_at = p.requested_topic, p.model, p.generated_at.isoformat()
    else:
        recorded = False
        relations, requested, model, generated_at = [], None, None, None
        try:
            chunks = chunks_from_hits(query_similar_chunks(question.text, subject_id, n_results=3))
            note = (
                "Written by the teacher (classified by AI when it was added), so there are no generation sources. "
                "Shown instead: the course-material passages most similar to it, retrieved now."
                if question.origin == "manual" else
                "Generation sources weren't recorded for this question (created before source tracking, or written by hand). "
                "Shown instead: the course-material passages most similar to it, retrieved now."
            )
        except Exception:
            chunks = []
            note = (
                "Written by the teacher, and similar course material couldn't be retrieved right now."
                if question.origin == "manual" else
                "Generation sources weren't recorded for this question, and similar material couldn't be retrieved right now."
            )
    return Evidence(
        question_id=question.id,
        recorded=recorded,
        note=note,
        requested_topic=requested,
        model=model,
        generated_at=generated_at,
        chunks=chunks,
        graph_relations=relations,
        topics=topics,
        bloom_level=int(question.bloom_level),
        difficulty_score=question.difficulty_score,
        difficulty=difficulty_bucket(question.difficulty_score),
        question_type=question.question_type.value,
        skill_category=question.effective_skill_category.value,
        co_ids=list(question.co_ids),
    )
