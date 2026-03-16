# apple-notes-pdf-mcp

An MCP server that gives LLMs access to your Apple Notes — including full-text extraction from PDF attachments.

Most Apple Notes integrations only expose note text. This server also reads PDF files attached to your notes using `pdfplumber`, so an LLM can search and reason over the actual content of receipts, papers, scanned documents, and anything else you've stashed in Notes.

## Quickstart

```bash
uvx apple-notes-pdf-mcp
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

## Tools

| Tool | Description |
|------|-------------|
| `list_notes` | List all notes (titles, folders, last-modified dates) |
| `search_notes` | Search notes by title or body text |
| `get_note` | Get the full text content of a single note |
| `get_note_with_pdfs` | Get note text plus extracted text from all PDF attachments |
| `list_attachments` | List all attachments for a given note |

## System Requirements

- **macOS 12+** (Monterey or later)
- **Python 3.10+**
- **Full Disk Access** granted to your terminal or application

## Permissions

This server is **read-only** — it never creates, modifies, or deletes notes. It reads directly from the Apple Notes SQLite database at `~/Library/Group Containers/group.com.apple.notes/`.

Your terminal (or the application running the MCP server) must have **Full Disk Access** enabled in System Settings > Privacy & Security > Full Disk Access. Without this, macOS will block access to the Notes database.
