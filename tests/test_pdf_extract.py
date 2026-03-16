import pytest
from apple_notes_pdf_mcp.pdf_extract import extract_pdf_text


def test_extract_text_from_sample_pdf(sample_pdf_path):
    result = extract_pdf_text(sample_pdf_path)
    assert result["text"] is not None
    assert len(result["text"]) > 0
    assert result["page_count"] > 0
    assert result["pages_extracted"] > 0
    assert result["error"] is None


def test_extract_with_max_pages(sample_pdf_path):
    result = extract_pdf_text(sample_pdf_path, max_pages=1)
    assert result["pages_extracted"] <= 1


def test_extract_nonexistent_file():
    result = extract_pdf_text("/nonexistent/path.pdf")
    assert result["text"] is None
    assert result["error"] == "not_downloaded"


def test_extract_non_pdf(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_text("not a pdf")
    result = extract_pdf_text(str(fake))
    assert result["text"] is None
    assert result["error"] is not None
