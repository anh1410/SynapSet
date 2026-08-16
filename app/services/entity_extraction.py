import warnings

import httpx
from google.genai import errors, types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.graph_store import KnowledgeGraphStore, normalize_topic_name
from app.core.llm import get_genai_client
from app.core.config import get_settings
from app.schemas.extraction import ExtractionResult
from app.services.document_extraction import TextChunk

EXTRACTION_PROMPT = """You are building a knowledge graph from course material for exam-question generation.

From the TEXT below, extract:
1. The distinct topics/concepts covered (keep names short and specific, e.g. "Parallel Computing" not "Computing").
2. Relationships between them:
   - PREREQUISITE_OF: topic A must be understood before topic B.
   - MAPS_TO: a topic maps to one of these Course Outcomes: {co_list}

Only extract relationships that are clearly supported by the text. Do not invent topics that aren't mentioned.

TEXT:
{text}"""


@retry(
    retry=retry_if_exception_type((errors.ServerError, errors.APIError, httpx.TransportError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def extract_from_chunk(chunk: TextChunk, course_outcomes: list[str] | None = None) -> ExtractionResult:
    """Run LLM-based entity/relation extraction on a single text chunk, retrying transient 5xx errors."""
    settings = get_settings()
    client = get_genai_client()

    co_list = ", ".join(course_outcomes) if course_outcomes else "(none provided)"
    prompt = EXTRACTION_PROMPT.format(co_list=co_list, text=chunk.text)

    response = client.models.generate_content(
        model=settings.generation_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractionResult,
        ),
    )

    if response.parsed is None:
        warnings.warn(f"Extraction returned no parsed result for chunk {chunk.chunk_index} of {chunk.source_document}")
        return ExtractionResult()

    return response.parsed


def merge_into_graph(
    result: ExtractionResult,
    graph_store: KnowledgeGraphStore,
    source_document: str,
) -> None:
    """Merge extracted topics/relations into the graph store, deduping by normalized name."""
    for topic in result.topics:
        node_id = normalize_topic_name(topic.name)
        if not node_id:
            continue
        if graph_store.graph.has_node(node_id):
            continue
        graph_store.add_topic(
            node_id,
            name=topic.name,
            description=topic.description,
            source_document=source_document,
        )

    for relation in result.relations:
        source_id = normalize_topic_name(relation.source)
        target_id = normalize_topic_name(relation.target)
        if not source_id or not target_id:
            continue
        if not graph_store.graph.has_node(source_id):
            graph_store.add_topic(source_id, name=relation.source, source_document=source_document)
        if not graph_store.graph.has_node(target_id):
            graph_store.add_topic(target_id, name=relation.target, source_document=source_document)
        graph_store.add_relation(source_id, target_id, relation.relation_type)


def ingest_chunks(
    chunks: list[TextChunk],
    graph_store: KnowledgeGraphStore,
    course_outcomes: list[str] | None = None,
) -> dict[str, float]:
    """Extract entities/relations from every chunk, merge into the graph, and score importance."""
    for chunk in chunks:
        result = extract_from_chunk(chunk, course_outcomes=course_outcomes)
        merge_into_graph(result, graph_store, source_document=chunk.source_document)

    scores = graph_store.compute_pagerank()
    for node_id, score in scores.items():
        graph_store.graph.nodes[node_id]["importance_score"] = score

    graph_store.save()
    return scores
