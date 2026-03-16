# CLAUDE.md

## Quick Start

```bash
uv sync                      # install dependencies
uv run pytest tests/ -v      # run tests
```

## Project Structure

`src/apple_notes_pdf_mcp/` contains four modules:

- **server.py** — MCP server (FastMCP) exposing 5 read-only tools to LLMs
- **applescript.py** — JXA (JavaScript for Automation) via `osascript` for Notes.app access
- **notestore.py** — SQLite queries against `NoteStore.sqlite` for note metadata and PDF attachment paths
- **pdf_extract.py** — PDF text extraction using `pdfplumber`

## Key Design Decisions

- **Read-only**: the server never writes to the Notes database or filesystem.
- **JXA over AppleScript**: JXA is used because it returns reliable JSON output; AppleScript string coercion is brittle.
- **ZACCOUNT column probing**: the NoteStore schema differs across macOS versions. The server probes for the correct `ZACCOUNT` column name at startup.
- **Glob for media paths**: on-disk PDF paths include an intermediate subdirectory that varies, so the code uses glob patterns to resolve attachment files.

## Testing Conventions

- `pytest` with tests in `tests/`.
- AppleScript/JXA tests mock `subprocess.run` to avoid requiring Notes.app at test time.
- NoteStore tests use SQLite fixture databases (in-memory or temp files) rather than the real NoteStore.
- Keep tests fast and side-effect-free; no network or disk writes.

## Tooling

- Build system: `hatchling`
- Package manager: `uv`
- MCP SDK: `mcp` (FastMCP)
