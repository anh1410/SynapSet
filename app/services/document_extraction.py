from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from docx import Document as DocxDocument
from pypdf import PdfReader


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    source_document: str
    page_number: int | None = None


def extract_text_from_pdf(path: str) -> str:
    """Extract text page by page using pdfplumber, falling back to pypdf on failure."""
    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages)
    except Exception:
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)


def extract_text_from_docx(path: str) -> str:
    doc = DocxDocument(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".txt":
        return Path(path).read_text(encoding="utf-8")
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(
    text: str,
    source_document: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[TextChunk]:
    """Split text into overlapping word-based chunks for embedding/retrieval."""
    words = text.split()
    if not words:
        return []

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    step = max(chunk_size - overlap, 1)

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(
            TextChunk(
                text=" ".join(chunk_words),
                chunk_index=index,
                source_document=source_document,
            )
        )
        index += 1
        start += step

    return chunks


def extract_and_chunk(path: str, chunk_size: int = 800, overlap: int = 150) -> list[TextChunk]:
    text = extract_text(path)
    return chunk_text(text, source_document=Path(path).name, chunk_size=chunk_size, overlap=overlap)
