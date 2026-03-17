"""MCP server entry point with tool definitions."""

from __future__ import annotations

import json
import os
import logging
import re

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ImageContent

from . import applescript, notestore, pdf_extract, image_extract

logger = logging.getLogger(__name__)


def _extract_note_pk(note_id: str) -> int | None:
    """Extract Z_PK from a note ID like x-coredata://UUID/ICNote/p123."""
    match = re.search(r'/p(\d+)$', note_id)
    return int(match.group(1)) if match else None


mcp = FastMCP("apple-notes-pdf")

# Resolve account column, store UUID, and DB path at startup
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
    with notestore.open_notestore(_db_path) as tmp_db:
        _account_col = notestore.find_account_column(tmp_db)
    logger.info("Using account column: %s", _account_col)


@mcp.tool()
def list_folders() -> str:
    """List all Apple Notes folders as a tree with note counts.

    Returns:
        JSON array of folder tree nodes, each with name, note_count,
        and children (nested folders).
    """
    _init_db()
    if not _db_path:
        return json.dumps([])

    with notestore.open_notestore(_db_path) as tmp_db:
        flat = notestore.list_folders(tmp_db)

    # Build tree from flat list
    by_pk: dict[int, dict] = {}
    roots: list[dict] = []
    for f in flat:
        node = {"name": f["name"], "note_count": f["note_count"], "children": []}
        by_pk[f["pk"]] = node
        if f["parent_pk"] is None:
            roots.append(node)
        else:
            parent = by_pk.get(f["parent_pk"])
            if parent:
                parent["children"].append(node)
            else:
                roots.append(node)

    return json.dumps(roots, indent=2)


@mcp.tool()
def search_notes(
    query: str = "",
    folder: str | None = None,
    sort_by: str = "modified",
    limit: int = 50,
    ascending: bool = False,
) -> str:
    """Search Apple Notes by title, body snippet, and attachment filenames.

    The primary discovery tool. Supports both targeted search and browsing:
    - With a query: FTS5 full-text search across titles, snippets, filenames,
      summaries, OCR text, and URLs. Returns ranked results with match_surface.
    - With an empty query: lists recent notes sorted by modification date
      (like a "list all" mode). Use sort_by, limit, and ascending to control.

    Args:
        query: Search string. Empty string returns recent notes (list mode).
        folder: Optional folder name to scope the search (includes subfolders).
        sort_by: Sort order for list mode -- "modified" (default).
        limit: Maximum number of notes to return (default 50).
        ascending: If True, sort oldest first. Default False (newest first).

    Returns:
        JSON array of note objects with id, title, snippet,
        modification_date, attachment_count, and note_url.
    """
    _init_db()

    # Empty or very short query -> list mode (return recent notes)
    if not query or len(query.strip()) < 2:
        if _db_path and _account_col:
            with notestore.open_notestore(_db_path) as tmp_db:
                notes = notestore.list_notes_sql(
                    tmp_db, _account_col,
                    sort_by=sort_by, limit=limit, folder_name=folder,
                    ascending=ascending,
                )
            return json.dumps(notes, indent=2)

        # Fallback to JXA if DB not available
        notes = applescript.list_notes(folder=folder)
        return json.dumps(notes, indent=2)

    # Non-empty query -> search mode
    if not _db_path or not _account_col:
        # Fall back to JXA search if DB not available
        results = applescript.search_notes(query)
        return json.dumps(results, indent=2)

    with notestore.open_notestore(_db_path) as tmp_db:
        try:
            results = notestore.search_notes_fts(
                tmp_db, _account_col, query, folder_name=folder, limit=limit,
            )
        except Exception:
            logger.warning("FTS5 search failed, falling back to LIKE-based search", exc_info=True)
            results = notestore.search_notes(
                tmp_db, _account_col, query, folder_name=folder, limit=limit,
            )

    return json.dumps(results, indent=2)


@mcp.tool()
def get_note(
    note_id: str,
    max_pages_per_pdf: int = 50,
    include_images: bool = True,
    max_image_size: int = 1_048_576,
) -> list[TextContent | ImageContent]:
    """Get a note's full body text with extracted PDF text and images.

    Returns the note body, extracted text from all embedded PDFs, and
    base64-encoded image attachments so an LLM can reason over both
    the note and its attachments in a single call.

    Args:
        note_id: The x-coredata:// identifier from search_notes.
        max_pages_per_pdf: Max pages to extract per PDF (default 50).
        include_images: Whether to include base64-encoded image attachments (default True).
        max_image_size: Max image file size in bytes before resizing (default 1MB).

    Returns:
        List of TextContent (JSON metadata) and ImageContent blocks for each image.
    """
    _init_db()

    # Get note body + metadata via AppleScript
    note = applescript.get_note(note_id)

    # Get note's Z_PK from the note_id
    note_pk = _extract_note_pk(note_id)

    pdf_attachments = []
    image_attachments_meta = []
    other_attachments = []
    image_contents = []

    note_url = None
    if note_pk and _db_path and _account_col:
        with notestore.open_notestore(_db_path) as tmp_db:
            pdf_rows = notestore.query_pdf_attachments(
                tmp_db, _account_col, note_pk
            )
            image_rows = notestore.query_image_attachments(
                tmp_db, _account_col, note_pk
            ) if include_images else []
            all_rows = notestore.query_all_attachments(
                tmp_db, _account_col, note_pk
            )
            identifier = notestore.get_note_identifier(tmp_db, note_pk)
            if identifier:
                note_url = f"https://james-andrews-coulter.github.io/apple-notes-pdf-mcp/?id={identifier}"

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

        # Encode image attachments
        for row in image_rows:
            file_path = notestore.resolve_media_path(
                row["account_id"], row["media_uuid"], row["filename"]
            )
            if file_path:
                img_result = image_extract.encode_image(file_path, max_size_bytes=max_image_size)
            else:
                img_result = {"data": None, "mime_type": None, "size_bytes": 0, "error": "not_downloaded"}

            image_attachments_meta.append({
                "filename": row["filename"],
                "mime_type": img_result["mime_type"],
                "size_bytes": img_result["size_bytes"],
                "error": img_result["error"],
            })

            if img_result["data"] and img_result["mime_type"]:
                image_contents.append(
                    ImageContent(
                        type="image",
                        data=img_result["data"],
                        mimeType=img_result["mime_type"],
                    )
                )

        # Non-PDF, non-image attachments go in other_attachments
        pdf_filenames = {r["filename"] for r in pdf_rows}
        image_filenames = {r["filename"] for r in image_rows}
        for row in all_rows:
            if row["filename"] not in pdf_filenames and row["filename"] not in image_filenames:
                other_attachments.append({
                    "name": row["filename"],
                    "type": row["uti"],
                })

    title = note.get("title", "")
    citation = f"[{title}]({note_url})" if note_url else title

    response = {
        "id": note.get("id"),
        "title": title,
        "body": note.get("body"),
        "folder": note.get("folder"),
        "modification_date": note.get("modification_date"),
        "note_url": note_url,
        "citation": citation,
        "pdf_attachments": pdf_attachments,
        "image_attachments": image_attachments_meta,
        "other_attachments": other_attachments,
    }

    result_blocks: list[TextContent | ImageContent] = [
        TextContent(type="text", text=json.dumps(response, indent=2)),
    ]
    result_blocks.extend(image_contents)

    return result_blocks


def main():
    """Entry point for the MCP server."""
    _init_db()
    mcp.run()


if __name__ == "__main__":
    main()
