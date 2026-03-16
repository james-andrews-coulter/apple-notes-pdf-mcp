"""MCP server entry point with tool definitions."""

from __future__ import annotations

import json
import os
import logging
import shutil

from mcp.server.fastmcp import FastMCP

from . import applescript, notestore, pdf_extract

logger = logging.getLogger(__name__)

mcp = FastMCP("apple-notes-pdf")

# Resolve account column and DB path at startup
_db_path: str | None = None
_account_col: str | None = None


def _init_db():
    global _db_path, _account_col
    if _db_path is not None:
        return
    _db_path = notestore.NOTESTORE_PATH
    if not os.path.exists(_db_path):
        logger.warning("NoteStore.sqlite not found at %s", _db_path)
        return
    tmp_db, tmp_dir = notestore._copy_db_to_temp(_db_path)
    try:
        _account_col = notestore.find_account_column(tmp_db)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    logger.info("Using account column: %s", _account_col)


@mcp.tool()
def list_notes(folder: str | None = None) -> str:
    """List all Apple Notes with basic metadata.

    Args:
        folder: Optional folder name to filter by.

    Returns:
        JSON array of note objects with id, title, folder, snippet,
        modification_date, and attachment_count.
    """
    notes = applescript.list_notes(folder=folder)
    return json.dumps(notes, indent=2)


@mcp.tool()
def search_notes(query: str) -> str:
    """Full-text search across Apple Notes bodies. Case-insensitive.

    Args:
        query: The search string to look for in note bodies.

    Returns:
        JSON array of matching note objects (same schema as list_notes).
    """
    results = applescript.search_notes(query)
    return json.dumps(results, indent=2)


@mcp.tool()
def get_note(note_id: str) -> str:
    """Get a single note's full body text and attachment metadata list.

    Args:
        note_id: The x-coredata:// identifier from list_notes.

    Returns:
        JSON object with id, title, body, folder, modification_date,
        and attachments array (name + type only, no content).
    """
    note = applescript.get_note(note_id)
    return json.dumps(note, indent=2)


@mcp.tool()
def get_note_with_pdfs(note_id: str, max_pages_per_pdf: int = 50) -> str:
    """Get a note's full body text WITH extracted text from all embedded PDFs.

    This is the key tool: it returns note body text and PDF content together
    so an LLM can reason over both the note and its attachments.

    Args:
        note_id: The x-coredata:// identifier from list_notes.
        max_pages_per_pdf: Max pages to extract per PDF (default 50).

    Returns:
        JSON with body, pdf_attachments (with extracted text),
        and other_attachments (metadata only).
    """
    _init_db()

    # Get note body + metadata via AppleScript
    note = applescript.get_note(note_id)

    # Get note's Z_PK from the note_id
    # The note_id is like x-coredata://UUID/ICNote/pNNN where NNN is the Z_PK
    note_pk = None
    if "/p" in note_id:
        try:
            note_pk = int(note_id.split("/p")[-1])
        except ValueError:
            pass

    pdf_attachments = []
    other_attachments = []

    if note_pk and _db_path and _account_col:
        tmp_db, tmp_dir = notestore._copy_db_to_temp(_db_path)
        try:
            pdf_rows = notestore.query_pdf_attachments(
                tmp_db, _account_col, note_pk
            )
            all_rows = notestore.query_all_attachments(
                tmp_db, _account_col, note_pk
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # Extract text from each PDF
        total_text_size = 0
        max_total_size = 500 * 1024  # 500KB limit

        for row in pdf_rows:
            file_path = notestore.resolve_media_path(
                row["account_id"], row["media_uuid"], row["filename"]
            )
            if file_path and os.path.exists(file_path):
                result = pdf_extract.extract_pdf_text(
                    file_path, max_pages=max_pages_per_pdf
                )
                if result["text"] and total_text_size + len(result["text"]) > max_total_size:
                    result["text"] = result["text"][:max_total_size - total_text_size]
                    result["error"] = "truncated_size_limit"
                if result["text"]:
                    total_text_size += len(result["text"])
            else:
                result = {
                    "text": None,
                    "page_count": 0,
                    "pages_extracted": 0,
                    "extraction_method": "pdfplumber",
                    "error": "not_downloaded",
                }

            pdf_attachments.append({
                "filename": row["filename"],
                **result,
            })

        # Non-PDF attachments
        pdf_filenames = {r["filename"] for r in pdf_rows}
        for row in all_rows:
            if row["filename"] not in pdf_filenames:
                other_attachments.append({
                    "name": row["filename"],
                    "type": row["uti"],
                })

    response = {
        "id": note.get("id"),
        "title": note.get("title"),
        "body": note.get("body"),
        "folder": note.get("folder"),
        "modification_date": note.get("modification_date"),
        "pdf_attachments": pdf_attachments,
        "other_attachments": other_attachments,
    }
    return json.dumps(response, indent=2)


@mcp.tool()
def list_attachments(note_id: str | None = None) -> str:
    """List all attachments across notes with resolved file paths.

    Useful for seeing what's available before calling get_note_with_pdfs.

    Args:
        note_id: Optional x-coredata:// id to filter to a single note.

    Returns:
        JSON array of attachment objects with note_title, filename,
        type, file_path, file_exists, and file_size_bytes.
    """
    _init_db()
    if not _db_path or not _account_col:
        return json.dumps([])

    note_pk = None
    if note_id and "/p" in note_id:
        try:
            note_pk = int(note_id.split("/p")[-1])
        except ValueError:
            pass

    tmp_db, tmp_dir = notestore._copy_db_to_temp(_db_path)
    try:
        rows = notestore.query_all_attachments(
            tmp_db, _account_col, note_pk=note_pk
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    results = []
    for row in rows:
        file_path = notestore.resolve_media_path(
            row["account_id"], row["media_uuid"], row["filename"]
        )
        file_exists = file_path is not None and os.path.exists(file_path)
        file_size = os.path.getsize(file_path) if file_exists else None

        results.append({
            "note_title": row["note_title"],
            "filename": row["filename"],
            "type": row["uti"],
            "file_path": file_path,
            "file_exists": file_exists,
            "file_size_bytes": file_size,
        })

    return json.dumps(results, indent=2)


def main():
    """Entry point for the MCP server."""
    _init_db()
    mcp.run()


if __name__ == "__main__":
    main()
