# apple-notes-pdf-mcp

An MCP server that gives LLMs access to your Apple Notes — including extracted text from PDF attachments.

Every existing Apple Notes integration only exposes note body text via AppleScript. This server goes further: it queries the NoteStore SQLite database to find PDF attachments, resolves their on-disk file paths, and extracts text with [pdfplumber](https://github.com/jsvine/pdfplumber). An LLM can search and reason over receipts, lab results, contracts, papers — anything you've attached to a note.

## Why this exists

AppleScript can tell you a PDF is attached to a note, but it can't read what the PDF says. This server bridges that gap by combining two access paths:

1. **AppleScript (JXA)** for note body text, titles, and metadata
2. **SQLite + filesystem** for resolving PDF file paths and extracting their content

The search is also SQLite-backed, meaning it finds notes by **title, body snippet, and attachment filename** — not just body text. A note titled "Followup appointment" with a PDF named "blood test results.pdf" will be found when you search for "blood test."

## Install

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "apple-notes-pdf": {
      "command": "uvx",
      "args": ["apple-notes-pdf-mcp"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add apple-notes-pdf -- uvx apple-notes-pdf-mcp
```

### Other MCP clients

```bash
uvx apple-notes-pdf-mcp
```

The server communicates over stdio using the [Model Context Protocol](https://modelcontextprotocol.io/).

## Tools

| Tool | Description |
|------|-------------|
| `list_notes` | List all notes with title, folder, modification date, and attachment count. Optional `folder` filter. |
| `search_notes` | Multi-surface search across note titles, body snippets, and attachment filenames. Returns `match_surface` indicating where the hit was found. |
| `get_note` | Get a single note's full plaintext body and attachment metadata list. |
| `get_note_with_pdfs` | **The key tool.** Returns note body text + extracted text from every embedded PDF, merged into a single response. Supports `max_pages_per_pdf` (default 50) and a 500KB total text limit. |
| `list_attachments` | List all attachments across notes with resolved file paths, existence checks, and file sizes. |

## Example

```
User: What was my ferritin level in my latest blood test?

Claude: I'll search your notes for blood test results.
→ search_notes("ferritin")
  Found "Followup Blood Test" (matched via attachment filename)

→ get_note_with_pdfs("x-coredata://…/ICNote/p11734")
  Extracted text from "iron ferritin blood test results.pdf"

Your ferritin level was 27 µg/L according to the iron studies panel
in your attached PDF.
```

## Requirements

- **macOS 12+** (Monterey or later)
- **Python 3.10+** (installed automatically via `uv`)
- **Full Disk Access** for your terminal app

### Granting Full Disk Access

System Settings → Privacy & Security → Full Disk Access → add Terminal / iTerm / Claude Desktop.

This is required because `NoteStore.sqlite` and the `Media/` directory live in a protected location (`~/Library/Group Containers/group.com.apple.notes/`). Without it, SQLite queries and PDF file reads will fail with permission errors.

### Automation permission

The first time the server runs, macOS will prompt you to allow your terminal to control Notes.app. Click **Allow**. This is needed for the AppleScript/JXA calls that read note body text.

## How it works

```
┌─────────────────────────────────────────┐
│  MCP Client (Claude Desktop / Code)     │
└──────────────────┬──────────────────────┘
                   │ MCP protocol (stdio)
┌──────────────────▼──────────────────────┐
│  apple-notes-pdf-mcp                    │
│                                         │
│  Tools:                                 │
│  ├─ list_notes        (JXA)             │
│  ├─ search_notes      (SQLite)          │
│  ├─ get_note          (JXA)             │
│  ├─ get_note_with_pdfs(JXA + SQLite)    │
│  └─ list_attachments  (SQLite)          │
│                                         │
│  Internal modules:                      │
│  ├─ applescript.py  → JXA wrappers      │
│  ├─ notestore.py    → SQLite queries    │
│  └─ pdf_extract.py  → pdfplumber        │
└────────┬─────────────────┬──────────────┘
         │                 │
         ▼                 ▼
   Notes.app         NoteStore.sqlite
   (JXA)             + Media/ files
```

### Key design decisions

- **Read-only.** The server never writes to the database, media files, or notes. All AppleScript calls are read operations. SQLite opens in read-only mode.
- **SQLite-first search.** AppleScript can only search body text. Our search queries SQLite across note titles (`ZTITLE1`), body snippets (`ZSNIPPET`), and attachment filenames (`ZFILENAME`) — finding notes that AppleScript search misses entirely.
- **WAL-safe DB access.** The NoteStore database is copied (with WAL and SHM files) to a temp directory before querying, avoiding lock contention with Notes.app.
- **ZACCOUNT column probing.** The column used for note→account joins varies across macOS versions (`ZACCOUNT2` through `ZACCOUNT8`). The server probes for the correct one at startup.
- **Intermediate subdirectory handling.** On-disk PDF paths include a variable intermediate directory (`Media/{uuid}/{sub_uuid}/{filename}`), resolved via glob.

## Error handling

| Scenario | Behavior |
|----------|----------|
| PDF not downloaded from iCloud | `"error": "not_downloaded"` for that attachment; others still extracted |
| Scanned/image-only PDF | `"error": "no_extractable_text"` — OCR is not supported in this version |
| Password-protected PDF | `"error": "encrypted_pdf"` |
| Notes.app not running | AppleScript auto-launches it (standard macOS behavior) |
| SQLite locked | DB is copied to temp dir first, so this shouldn't occur |
| Total text exceeds 500KB | Text is truncated with `"error": "truncated_size_limit"` |

## Development

```bash
git clone https://github.com/james-andrews-coulter/apple-notes-pdf-mcp.git
cd apple-notes-pdf-mcp
uv sync
uv run pytest tests/ -v
```

### Project structure

```
src/apple_notes_pdf_mcp/
├── server.py         # MCP server, tool definitions
├── applescript.py    # JXA wrappers for Notes.app
├── notestore.py      # SQLite queries against NoteStore.sqlite
└── pdf_extract.py    # pdfplumber text extraction
tests/
├── test_applescript.py   # Mocked JXA tests
├── test_notestore.py     # SQLite fixture tests
└── test_pdf_extract.py   # PDF extraction tests
```

## Limitations

These are explicitly out of scope for v0.1:

- **OCR for scanned PDFs** — would require Tesseract or similar
- **Image attachment content** — could add Vision API pass-through later
- **Write operations** — no creating, editing, or deleting notes
- **Rich text / HTML** — body is returned as plaintext only
- **Cross-platform** — macOS only (Apple Notes on iOS/iPadOS is not addressable via MCP)

## License

MIT
