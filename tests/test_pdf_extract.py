from apple_notes_pdf_mcp.pdf_extract import extract_pdf_text


def test_extract_text(sample_pdf_path):
    result = extract_pdf_text(sample_pdf_path)
    assert result["text"] is not None
    assert result["page_count"] > 0
    assert result["error"] is None


def test_extract_missing_file():
    result = extract_pdf_text("/nonexistent/path.pdf")
    assert result["text"] is None
    assert result["error"] == "not_downloaded"
