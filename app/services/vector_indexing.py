from app.core.llm import embed_text
from app.core.vector_store import get_collection
from app.services.document_extraction import TextChunk


def _chunk_id(chunk: TextChunk) -> str:
    return f"{chunk.source_document}::{chunk.chunk_index}"


def index_chunks(chunks: list[TextChunk]) -> None:
    """Embed each chunk and upsert it into the vector store."""
    if not chunks:
        return

    collection = get_collection()
    ids = [_chunk_id(c) for c in chunks]
    embeddings = [embed_text(c.text) for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {"source_document": c.source_document, "chunk_index": c.chunk_index} for c in chunks
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def query_similar_chunks(query: str, n_results: int = 5) -> list[dict]:
    """Return the top-n chunks (text + metadata + distance) most similar to the query."""
    collection = get_collection()
    query_embedding = embed_text(query)

    results = collection.query(query_embeddings=[query_embedding], n_results=n_results)

    hits = []
    for doc, meta, distance in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"text": doc, "metadata": meta, "distance": distance})
    return hits
