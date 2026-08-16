from pathlib import Path

import pytest

from app.services.document_extraction import chunk_text, extract_text, extract_text_from_pdf, extract_text_from_pptx

SAMPLE_PPTX = Path("data/uploads/CC/unit1.pptx")
SAMPLE_PDF = Path("data/uploads/CC/unit1QB.pdf")


def test_chunk_text_basic():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, source_document="test.txt", chunk_size=20, overlap=5)
    assert len(chunks) > 1
    assert chunks[0].chunk_index == 0
    assert all(c.source_document == "test.txt" for c in chunks)


def test_chunk_text_overlap():
    text = " ".join(f"w{i}" for i in range(30))
    chunks = chunk_text(text, source_document="t", chunk_size=10, overlap=3)
    assert chunks[0].text.split()[-3:] == chunks[1].text.split()[:3]


def test_chunk_text_empty():
    assert chunk_text("", source_document="t") == []


def test_extract_text_unsupported_extension(tmp_path):
    path = tmp_path / "file.xyz"
    path.write_text("hello")
    with pytest.raises(ValueError):
        extract_text(str(path))


def test_extract_text_legacy_ppt_rejected(tmp_path):
    path = tmp_path / "file.ppt"
    path.write_bytes(b"fake")
    with pytest.raises(ValueError, match="Legacy .ppt"):
        extract_text(str(path))


@pytest.mark.skipif(not SAMPLE_PPTX.exists(), reason="sample course file not present locally")
def test_extract_real_pptx():
    text = extract_text_from_pptx(str(SAMPLE_PPTX))
    assert len(text) > 500


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample course file not present locally")
def test_extract_real_pdf():
    text = extract_text_from_pdf(str(SAMPLE_PDF))
    assert len(text) > 100
