"""PDF text extraction using pdfplumber."""

from __future__ import annotations

import os

import pdfplumber


def extract_pdf_text(
    file_path: str,
    max_pages: int = 50,
) -> dict:
    """Extract text from a PDF file.

    Returns dict with keys: text, page_count, pages_extracted,
    extraction_method, error.
    """
    if not os.path.exists(file_path):
        return {
            "text": None,
            "page_count": 0,
            "pages_extracted": 0,
            "extraction_method": "pdfplumber",
            "error": "not_downloaded",
        }

    try:
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            pages_to_extract = min(page_count, max_pages)
            texts = []
            for page in pdf.pages[:pages_to_extract]:
                text = page.extract_text()
                if text:
                    texts.append(text)

            full_text = "\n\n".join(texts) if texts else None
            error = None if full_text else "no_extractable_text"

            return {
                "text": full_text,
                "page_count": page_count,
                "pages_extracted": pages_to_extract,
                "extraction_method": "pdfplumber",
                "error": error,
            }
    except Exception as e:
        error_type = "encrypted_pdf" if "encrypted" in str(e).lower() else str(e)
        return {
            "text": None,
            "page_count": 0,
            "pages_extracted": 0,
            "extraction_method": "pdfplumber",
            "error": error_type,
        }
