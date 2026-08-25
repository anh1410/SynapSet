import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_teacher
from app.core.config import get_settings
from app.core.document_store import get_document_store
from app.core.graph_store import get_graph_store
from app.core.question_bank import get_question_bank
from app.schemas.document import DocumentCategory, UploadedDocument
from app.services.document_cleanup import remove_document_from_graph
from app.services.document_extraction import extract_and_chunk, extract_and_chunk_for_extraction
from app.services.entity_extraction import extract_from_chunk, merge_into_graph
from app.services.topic_dedup import merge_duplicate_topics
from app.services.vector_indexing import delete_document_chunks, index_chunks

router = APIRouter(prefix="/api/v1/graph", tags=["graph"], dependencies=[Depends(get_current_teacher)])


class IngestResponse(BaseModel):
    document: UploadedDocument
    retrieval_chunks_indexed: int
    extraction_chunks_processed: int
    graph_nodes: int
    graph_edges: int


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    category: DocumentCategory = Form(...),
    course_outcomes: str | None = Form(None, description="Comma-separated CO codes, e.g. 'CO1,CO2'"),
) -> IngestResponse:
    """Upload a syllabus/notes/question-paper file, index it for retrieval, and extend the knowledge graph."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename

    contents = await file.read()
    dest.write_bytes(contents)

    doc_store = get_document_store()
    document = UploadedDocument(
        id=str(uuid.uuid4()), filename=file.filename, category=category, size_bytes=len(contents)
    )
    doc_store.add(document)

    try:
        co_list = [c.strip() for c in course_outcomes.split(",") if c.strip()] if course_outcomes else None

        retrieval_chunks = extract_and_chunk(str(dest))
        index_chunks(retrieval_chunks)

        extraction_chunks = extract_and_chunk_for_extraction(str(dest))
        graph_store = get_graph_store()
        nodes_before = set(graph_store.graph.nodes)
        for chunk in extraction_chunks:
            result = extract_from_chunk(chunk, course_outcomes=co_list)
            merge_into_graph(result, graph_store, source_document=chunk.source_document)

        scores = graph_store.compute_pagerank()
        for node_id, score in scores.items():
            graph_store.graph.nodes[node_id]["importance_score"] = score
        graph_store.save()

        new_topics = len(set(graph_store.graph.nodes) - nodes_before)
        document.status = "processed"
        document.topics_extracted = new_topics
        doc_store.add(document)

        return IngestResponse(
            document=document,
            retrieval_chunks_indexed=len(retrieval_chunks),
            extraction_chunks_processed=len(extraction_chunks),
            graph_nodes=graph_store.graph.number_of_nodes(),
            graph_edges=graph_store.graph.number_of_edges(),
        )
    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)
        doc_store.add(document)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


@router.get("/documents", response_model=list[UploadedDocument])
def list_documents() -> list[UploadedDocument]:
    return get_document_store().list()


@router.delete("/documents/{document_id}")
def delete_document(document_id: str) -> dict:
    store = get_document_store()
    document = store.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    graph_store = get_graph_store()
    cleanup = remove_document_from_graph(graph_store, document.filename)
    if cleanup["nodes_removed"] or cleanup["edges_removed"]:
        scores = graph_store.compute_pagerank()
        for node_id, score in scores.items():
            graph_store.graph.nodes[node_id]["importance_score"] = score
    graph_store.save()

    delete_document_chunks(document.filename)

    store.remove(document_id)
    return {"deleted": document_id, **cleanup}


class GraphNodeOut(BaseModel):
    id: str
    name: str
    description: str = ""
    importance_score: float = 0.0
    question_count: int = 0
    coverage_pct: int = 0
    degree: int = 0
    neglected: bool = False


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    relation_type: str


class GraphResponse(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


@router.get("", response_model=GraphResponse)
def get_graph() -> GraphResponse:
    """Full knowledge graph enriched with question-bank coverage stats per topic."""
    graph_store = get_graph_store()
    graph = graph_store.graph
    bank = get_question_bank()

    question_counts: dict[str, int] = {}
    for q in bank.list():
        for topic_id in q.topic_ids:
            question_counts[topic_id] = question_counts.get(topic_id, 0) + 1
    max_count = max(question_counts.values(), default=0)

    nodes = []
    for node_id, data in graph.nodes(data=True):
        count = question_counts.get(node_id, 0)
        coverage_pct = round(100 * count / max_count) if max_count else 0
        nodes.append(
            GraphNodeOut(
                id=node_id,
                name=data.get("name", node_id),
                description=data.get("description", ""),
                importance_score=data.get("importance_score", 0.0),
                question_count=count,
                coverage_pct=coverage_pct,
                degree=graph.degree(node_id),
                neglected=coverage_pct < 40,
            )
        )

    edges = [
        GraphEdgeOut(source=u, target=v, relation_type=d.get("relation_type", ""))
        for u, v, d in graph.edges(data=True)
    ]

    return GraphResponse(nodes=nodes, edges=edges)


class DedupeTopicsResponse(BaseModel):
    merged_groups: int
    nodes_removed: int
    questions_updated: int


@router.post("/dedupe-topics", response_model=DedupeTopicsResponse)
def dedupe_topics() -> DedupeTopicsResponse:
    """Merge near-duplicate topic nodes (e.g. singular/plural variants from
    repeated ingestion) into a single canonical node."""
    result = merge_duplicate_topics(get_graph_store(), get_question_bank())
    return DedupeTopicsResponse(**result)
