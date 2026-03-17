# Agent Configuration & Usage Guide

This guide explains how to configure an LLM agent to effectively use the apple-notes-pdf-mcp tools.

## Agent Navigation Workflow

The recommended pattern for an agent interacting with Apple Notes:

1. **`list_folders`** -- Understand the folder structure and where notes live.
2. **`search_notes(query, folder=...)`** -- Targeted FTS5 search within a specific folder tree. With an empty query, lists recent notes.
3. **`get_note(note_id)`** -- Retrieve the full note body, extracted PDF text, and inline images.

This three-step flow lets the agent orient itself, find the right note, and then retrieve all content in a single call.

## Folder-Scoped Agent Configuration

When building a domain-specific agent, scope it to a folder subtree. Here is a system prompt template for a health research agent:

```
You are a health research assistant with access to Apple Notes.

SCOPE: Only search within the "Health & Fitness" folder and its subfolders.
Always start by calling list_folders to understand the folder structure.
When searching, use the folder parameter: search_notes(query, folder="Health & Fitness")

CITATIONS: Every tool response includes a `citation` field with a pre-formatted
markdown link. Copy it verbatim into your response when referencing a note.
When citing multiple notes, include all citation links.

NAVIGATION: If initial search returns few results:
1. Check list_folders for relevant subfolders
2. Broaden the search to parent folder
3. Try different search terms (FTS5 supports prefix matching with *)
4. If documents may be in a foreign language, try searching in that language too
```

## Citation Pattern

All tool responses include a `citation` field containing a pre-formatted markdown link:

```
[Note Title](https://your-redirect.github.io/notes-link/?id=UUID)
```

The link is an HTTPS URL that redirects to open the note in Notes.app. It automatically detects iOS vs macOS and uses the correct URI scheme (`mobilenotes://` or `notes://`).

**Agents should copy the `citation` field verbatim** -- do not reconstruct the link manually.

### Multiple sources

When a query involves multiple notes, each result has its own `citation`. Include all of them:

```
Dec 2025: Ferritin 50.3 ug/L -- [annual blood test results](https://.../?id=A9B5...)
Feb 2026: Ferritin 27 ug/L -- [Followup Blood Test](https://.../?id=5391...)
Ongoing plan -- [Iron deficiency plan](https://.../?id=9D8C...)
```

### Self-hosting the redirect

The default `citation` URLs point to a GitHub Pages redirect. To self-host, deploy the single-file redirect page from [notes-link](https://github.com/james-andrews-coulter/notes-link) and update the URL base in `notestore.py`.

## Search Tips

The `search_notes` tool uses SQLite FTS5 (full-text search) under the hood. Key capabilities:

- **Porter stemming**: "running" matches "run", "runs", "runner".
- **Prefix matching**: `blood*` matches "blood", "bloodwork", "bloody".
- **Multi-surface search**: Queries match against note titles, body snippets, attachment filenames, note summaries, OCR summaries, and URLs.
- **Folder scoping**: Use the `folder` parameter to restrict results to a folder and all its subfolders.
- **Ranked results**: FTS5 returns results ranked by relevance, not just modification date.
- **Multilingual content**: FTS5 indexes whatever text is stored. If notes contain foreign-language documents, search in that language too.

If FTS5 is unavailable (e.g., older SQLite build), the server automatically falls back to LIKE-based search.

## Available Tools Reference

| Tool | Parameters | Description |
|------|-----------|-------------|
| `search_notes` | `query=""`, `folder=None`, `sort_by="modified"`, `limit=50`, `ascending=False` | The primary discovery tool. With a query: FTS5-backed multi-surface search. With an empty query: lists recent notes sorted by modification date. Every result includes a `citation` field. |
| `get_note` | `note_id`, `max_pages_per_pdf=50`, `include_images=True`, `max_image_size=1048576` | Full body + extracted PDF text + base64-encoded images. Includes a `citation` field. |
| `list_folders` | _(none)_ | Folder tree with note counts per folder. Use to understand the folder hierarchy before searching. |
