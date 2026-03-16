# Agent Configuration & Usage Guide

This guide explains how to configure an LLM agent to effectively use the apple-notes-pdf-mcp tools.

## Agent Navigation Workflow

The recommended pattern for an agent interacting with Apple Notes:

1. **`list_folders`** -- Understand the folder structure and where notes live.
2. **`search_notes(query, folder=...)`** -- Targeted FTS5 search within a specific folder tree.
3. **`get_note_with_attachments`** -- Retrieve the full note body, extracted PDF text, and inline images.

This three-step flow lets the agent orient itself, find the right note, and then retrieve all content in a single call.

## Folder-Scoped Agent Configuration

When building a domain-specific agent, scope it to a folder subtree. Here is a system prompt template for a health research agent:

```
You are a health research assistant with access to Apple Notes.

SCOPE: Only search within the "Health & Fitness" folder and its subfolders.
Always start by calling list_folders to understand the folder structure.
When searching, use the folder parameter: search_notes(query, folder="Health & Fitness")

CITATIONS: When referencing information from notes, always include:
- The note title
- A clickable link using the note_url field: [Note Title](note_url)
- The source context (which part of the note or which PDF attachment)

NAVIGATION: If initial search returns few results:
1. Check list_folders for relevant subfolders
2. Broaden the search to parent folder
3. Try different search terms (FTS5 supports prefix matching with *)
```

## Citation Pattern

All tool responses include a `note_url` field with the format:

```
applenotes://showNote?noteId={UUID}
```

This deep link works across Apple platforms:

- **macOS**: Opens Notes.app directly to the note.
- **iOS/iPadOS**: Opens the Notes app directly to the note.
- **Telegram, Slack, or other chat**: Include as a markdown link so the user can tap through:
  ```
  [Note Title](applenotes://showNote?noteId=UUID)
  ```

Agents should always cite sources with this link so users can verify information against the original note.

## Search Tips

The `search_notes` tool uses SQLite FTS5 (full-text search) under the hood. Key capabilities:

- **Porter stemming**: "running" matches "run", "runs", "runner".
- **Prefix matching**: `blood*` matches "blood", "bloodwork", "bloody".
- **Multi-surface search**: Queries match against note titles, body snippets, attachment filenames, note summaries, OCR summaries, and URLs.
- **Folder scoping**: Use the `folder` parameter to restrict results to a folder and all its subfolders.
- **Ranked results**: FTS5 returns results ranked by relevance, not just modification date.

If FTS5 is unavailable (e.g., older SQLite build), the server automatically falls back to LIKE-based search.

## Available Tools Reference

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_notes` | `sort_by="modified"`, `limit=50`, `folder=None` | List notes with metadata. Sort by `"modified"` (newest first) or `"title"` (A-Z). Filter by folder subtree. |
| `search_notes` | `query`, `folder=None` | FTS5-backed multi-surface search across titles, snippets, filenames, summaries, OCR text, and URLs. |
| `get_note` | `note_id` | Full plaintext body + attachment metadata list (no content extraction). |
| `get_note_with_attachments` | `note_id`, `max_pages_per_pdf=50`, `include_images=True`, `max_image_size=1048576` | Full body + extracted PDF text + base64-encoded images. The primary tool for deep content retrieval. |
| `get_note_with_pdfs` | _(same as above)_ | Backward-compatible alias for `get_note_with_attachments`. |
| `list_attachments` | `note_id=None` | List all attachments with resolved file paths, existence checks, and file sizes. Filter to a single note with `note_id`. |
| `list_folders` | _(none)_ | Folder tree with note counts per folder. Use to understand the folder hierarchy before searching. |
