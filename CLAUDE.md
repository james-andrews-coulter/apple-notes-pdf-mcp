# CLAUDE.md

## Quick Start

```bash
uv sync                      # install dependencies
uv run pytest tests/ -v      # run tests
```

## Project Structure

`src/apple_notes_pdf_mcp/` contains five modules:

- **server.py** -- MCP server (FastMCP) exposing 3 read-only tools to LLMs
- **applescript.py** -- JXA (JavaScript for Automation) via `osascript` for Notes.app access
- **notestore.py** -- SQLite queries + FTS5 full-text search against `NoteStore.sqlite` for note metadata, attachment paths, folder trees, and deep links via ZIDENTIFIER
- **pdf_extract.py** -- PDF text extraction using `pdfplumber`
- **image_extract.py** -- Image encoding (HEIC/PNG/JPEG) via macOS `sips` + base64 for MCP ImageContent

## Key Design Decisions

- **Read-only**: the server never writes to the Notes database or filesystem. FTS5 index is built on a temp copy.
- **JXA over AppleScript**: JXA is used because it returns reliable JSON output; AppleScript string coercion is brittle.
- **FTS5 search**: A virtual FTS5 table with Porter stemming is created at search time on the temp DB copy. Indexes titles, snippets, filenames, summaries, OCR summaries, and URLs. Falls back to LIKE-based search if FTS5 is unavailable.
- **Image support via sips**: HEIC images are converted to JPEG using macOS's built-in `sips` tool. Images over the size limit are resized. Returned as base64-encoded MCP `ImageContent` blocks.
- **Deep links via ZIDENTIFIER**: Every note response includes an `applenotes://showNote?noteId={UUID}` URL. Works on macOS and iOS.
- **ZACCOUNT column probing**: the NoteStore schema differs across macOS versions. The server probes for the correct `ZACCOUNT` column name at startup.
- **Glob for media paths**: on-disk attachment paths include an intermediate subdirectory that varies, so the code uses glob patterns to resolve attachment files.

## Testing Conventions

- `pytest` with tests in `tests/`.
- AppleScript/JXA tests mock `subprocess.run` to avoid requiring Notes.app at test time.
- NoteStore tests use SQLite fixture databases (in-memory or temp files) rather than the real NoteStore.
- Image tests mock `sips` subprocess calls.
- Keep tests fast and side-effect-free; no network or disk writes.

## Tooling

- Build system: `hatchling`
- Package manager: `uv`
- MCP SDK: `mcp` (FastMCP)
