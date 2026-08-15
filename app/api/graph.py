import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.graph_store import get_graph_store
from app.services.document_extraction import extract_and_chunk, extract_and_chunk_for_extraction
from app.services.entity_extraction import extract_from_chunk, merge_into_graph
from app.services.vector_indexing import index_chunks

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


class IngestResponse(BaseModel):
    filename: str
    retrieval_chunks_indexed: int
    extraction_chunks_processed: int
    graph_nodes: int
    graph_edges: int


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    course_outcomes: str | None = Form(None, description="Comma-separated CO codes, e.g. 'CO1,CO2'"),
) -> IngestResponse:
    """Upload a syllabus/notes file, index it for retrieval, and extend the knowledge graph."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    co_list = [c.strip() for c in course_outcomes.split(",") if c.strip()] if course_outcomes else None

    retrieval_chunks = extract_and_chunk(str(dest))
    index_chunks(retrieval_chunks)

    extraction_chunks = extract_and_chunk_for_extraction(str(dest))
    graph_store = get_graph_store()
    for chunk in extraction_chunks:
        result = extract_from_chunk(chunk, course_outcomes=co_list)
        merge_into_graph(result, graph_store, source_document=chunk.source_document)

    scores = graph_store.compute_pagerank()
    for node_id, score in scores.items():
        graph_store.graph.nodes[node_id]["importance_score"] = score
    graph_store.save()

    return IngestResponse(
        filename=file.filename,
        retrieval_chunks_indexed=len(retrieval_chunks),
        extraction_chunks_processed=len(extraction_chunks),
        graph_nodes=graph_store.graph.number_of_nodes(),
        graph_edges=graph_store.graph.number_of_edges(),
    )


class GraphSummaryResponse(BaseModel):
    nodes: int
    edges: int
    top_topics: list[dict]


@router.get("/summary", response_model=GraphSummaryResponse)
def graph_summary() -> GraphSummaryResponse:
    graph_store = get_graph_store()
    graph = graph_store.graph
    top = sorted(
        ({"name": d.get("name", n), "importance_score": d.get("importance_score", 0.0)} for n, d in graph.nodes(data=True)),
        key=lambda t: -t["importance_score"],
    )[:10]
    return GraphSummaryResponse(nodes=graph.number_of_nodes(), edges=graph.number_of_edges(), top_topics=top)
