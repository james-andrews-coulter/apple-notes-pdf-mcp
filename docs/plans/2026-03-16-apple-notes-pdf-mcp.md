# Apple Notes PDF MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an MCP server that returns Apple Notes body text AND extracted PDF attachment content in a single tool call.

**Architecture:** Hybrid AppleScript (via `osascript`) for note text/metadata + SQLite queries against `NoteStore.sqlite` to resolve PDF attachment file paths + `pdfplumber` for text extraction. Five MCP tools: `list_notes`, `search_notes`, `get_note`, `get_note_with_pdfs`, `list_attachments`.

**Tech Stack:** Python 3.10+, `mcp` SDK (PyPI), `pdfplumber`, `sqlite3` (stdlib), `subprocess` for osascript, `pyproject.toml` + `uv` for packaging.

**Key discovery:** On this machine, the correct ZACCOUNT column for the note→account join is `ZACCOUNT7` (varies by macOS version — must probe at startup). Also, the on-disk path has an intermediate subdirectory: `Accounts/{account_id}/Media/{media_uuid}/{sub_uuid}/{filename}` — we must glob for the file.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/apple_notes_pdf_mcp/__init__.py`
- Create: `README.md`

**Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "apple-notes-pdf-mcp"
version = "0.1.0"
description = "MCP server for Apple Notes with PDF attachment content extraction"
requires-python = ">=3.10"
dependencies = [
    "mcp[cli]>=1.0.0",
    "pdfplumber>=0.11.0",
]

[project.scripts]
apple-notes-pdf-mcp = "apple_notes_pdf_mcp.server:main"
```

**Step 2: Create `src/apple_notes_pdf_mcp/__init__.py`**

Empty file.

**Step 3: Create `README.md`**

Include: what it does, quickstart with `uvx`, Claude Desktop config snippet, Full Disk Access requirement, Claude Code install command.

**Step 4: Commit**

```bash
git add pyproject.toml src/ README.md
git commit -m "chore: scaffold project with pyproject.toml and package structure"
```

---

### Task 2: PDF Extraction Module (`pdf_extract.py`)

**Files:**
- Create: `src/apple_notes_pdf_mcp/pdf_extract.py`
- Create: `tests/test_pdf_extract.py`
- Create: `tests/fixtures/sample.pdf`

**Step 1: Create sample PDF fixture**

```python
# Script to generate tests/fixtures/sample.pdf
from pdfplumber import open as _  # just verify import works
# Use reportlab or just include a pre-made PDF
# Simpler: create a minimal PDF with fpdf2 or just write raw PDF bytes
```

Actually, create the fixture with a simple Python script using `pdfplumber`'s own test approach — write a minimal valid PDF with known text content.

**Step 2: Write failing tests in `tests/test_pdf_extract.py`**

```python
import pytest
from apple_notes_pdf_mcp.pdf_extract import extract_pdf_text


def test_extract_text_from_sample_pdf(sample_pdf_path):
    result = extract_pdf_text(sample_pdf_path)
    assert result["text"] is not None
    assert "sample" in result["text"].lower() or len(result["text"]) > 0
    assert result["page_count"] > 0
    assert result["pages_extracted"] > 0
    assert result["error"] is None


def test_extract_with_max_pages(sample_pdf_path):
    result = extract_pdf_text(sample_pdf_path, max_pages=1)
    assert result["pages_extracted"] <= 1


def test_extract_nonexistent_file():
    result = extract_pdf_text("/nonexistent/path.pdf")
    assert result["text"] is None
    assert result["error"] == "not_downloaded"


def test_extract_non_pdf(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_text("not a pdf")
    result = extract_pdf_text(str(fake))
    assert result["text"] is None
    assert result["error"] is not None
```

**Step 3: Run tests — expect FAIL (module not found)**

```bash
cd /Users/jamesalexander/Developer/apple-notes-pdf-mcp
uv run pytest tests/test_pdf_extract.py -v
```

**Step 4: Implement `pdf_extract.py`**

```python
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
```

**Step 5: Create conftest with sample PDF fixture**

Create `tests/conftest.py`:

```python
import pytest
import subprocess

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a minimal PDF with known text content."""
    pdf_path = tmp_path / "sample.pdf"
    # Use Python to create a minimal PDF
    content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj
4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
5 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td (Sample PDF text) Tj ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000340 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
434
%%EOF"""
    pdf_path.write_bytes(content)
    return str(pdf_path)
```

**Step 6: Run tests — expect PASS**

```bash
uv run pytest tests/test_pdf_extract.py -v
```

**Step 7: Commit**

```bash
git add src/apple_notes_pdf_mcp/pdf_extract.py tests/
git commit -m "feat: add PDF text extraction module with pdfplumber"
```

---

### Task 3: NoteStore SQLite Module (`notestore.py`)

**Files:**
- Create: `src/apple_notes_pdf_mcp/notestore.py`
- Create: `tests/test_notestore.py`

**Step 1: Write failing tests in `tests/test_notestore.py`**

Test against an in-memory SQLite fixture that mimics the NoteStore schema.

```python
import sqlite3
import pytest
from apple_notes_pdf_mcp.notestore import (
    find_account_column,
    query_pdf_attachments,
    query_all_attachments,
)


@pytest.fixture
def notestore_db(tmp_path):
    """Create a minimal NoteStore.sqlite fixture."""
    db_path = tmp_path / "NoteStore.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE ZICCLOUDSYNCINGOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            Z_ENT INTEGER,
            ZTITLE1 TEXT,
            ZMEDIA INTEGER,
            ZNOTE INTEGER,
            ZFILENAME TEXT,
            ZIDENTIFIER TEXT,
            ZTYPEUTI TEXT,
            ZACCOUNT4 INTEGER
        )
    """)
    # Insert account (Z_PK=1)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZIDENTIFIER)
        VALUES (1, 'LocalAccount')
    """)
    # Insert note (Z_PK=2, ZACCOUNT4=1)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZACCOUNT4)
        VALUES (2, 'Test Note', 1)
    """)
    # Insert media (Z_PK=3)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER)
        VALUES (3, 'doc.pdf', 'MEDIA-UUID-123')
    """)
    # Insert attachment (Z_PK=4, ZMEDIA=3, ZNOTE=2)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI)
        VALUES (4, 3, 2, 'com.adobe.pdf')
    """)
    # Insert non-PDF attachment (Z_PK=5, ZMEDIA=6, ZNOTE=2)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER)
        VALUES (6, 'photo.jpg', 'MEDIA-UUID-456')
    """)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI)
        VALUES (5, 6, 2, 'public.jpeg')
    """)
    conn.commit()
    conn.close()
    return str(db_path)


def test_find_account_column(notestore_db):
    col = find_account_column(notestore_db)
    assert col == "ZACCOUNT4"


def test_query_pdf_attachments(notestore_db):
    results = query_pdf_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    assert len(results) == 1
    assert results[0]["filename"] == "doc.pdf"
    assert results[0]["media_uuid"] == "MEDIA-UUID-123"
    assert results[0]["account_id"] == "LocalAccount"
    assert results[0]["uti"] == "com.adobe.pdf"


def test_query_pdf_attachments_no_match(notestore_db):
    results = query_pdf_attachments(notestore_db, "ZACCOUNT4", note_pk=999)
    assert results == []


def test_query_all_attachments(notestore_db):
    results = query_all_attachments(notestore_db, "ZACCOUNT4")
    assert len(results) == 2
    types = {r["uti"] for r in results}
    assert "com.adobe.pdf" in types
    assert "public.jpeg" in types


def test_query_all_attachments_filtered(notestore_db):
    results = query_all_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    assert len(results) == 2
```

**Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_notestore.py -v
```

**Step 3: Implement `notestore.py`**

```python
"""SQLite queries against Apple Notes NoteStore.sqlite."""

from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import tempfile


NOTESTORE_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
)

MEDIA_BASE = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.notes"
)


def _copy_db_to_temp(db_path: str) -> tuple[str, str]:
    """Copy DB and WAL to temp dir to avoid lock contention."""
    tmp_dir = tempfile.mkdtemp(prefix="notes_mcp_")
    dest = os.path.join(tmp_dir, "NoteStore.sqlite")
    shutil.copy2(db_path, dest)
    wal = db_path + "-wal"
    if os.path.exists(wal):
        shutil.copy2(wal, os.path.join(tmp_dir, "NoteStore.sqlite-wal"))
    shm = db_path + "-shm"
    if os.path.exists(shm):
        shutil.copy2(shm, os.path.join(tmp_dir, "NoteStore.sqlite-shm"))
    return dest, tmp_dir


def find_account_column(db_path: str) -> str:
    """Probe ZICCLOUDSYNCINGOBJECT to find the correct ZACCOUNT column.

    The column used for note→account joins varies by macOS version.
    We try ZACCOUNT2 through ZACCOUNT8 and find which one produces
    valid join results.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = [
            r[1]
            for r in conn.execute(
                "PRAGMA table_info(ZICCLOUDSYNCINGOBJECT)"
            ).fetchall()
        ]
        candidates = sorted(
            [c for c in cols if c.startswith("ZACCOUNT") and c[8:].isdigit()],
            key=lambda c: int(c[8:]),
        )

        for col in candidates:
            try:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM ZICCLOUDSYNCINGOBJECT note
                    JOIN ZICCLOUDSYNCINGOBJECT acc ON acc.Z_PK = note.{col}
                    WHERE note.ZTITLE1 IS NOT NULL
                      AND acc.ZIDENTIFIER IS NOT NULL
                    """,
                ).fetchone()
                if row and row[0] > 0:
                    return col
            except sqlite3.OperationalError:
                continue

        return "ZACCOUNT4"  # fallback
    finally:
        conn.close()


def query_pdf_attachments(
    db_path: str,
    account_col: str,
    note_pk: int,
) -> list[dict]:
    """Query PDF attachments for a specific note."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"""
            SELECT
                note.ZTITLE1    AS note_title,
                note.Z_PK       AS note_pk,
                media.ZFILENAME AS filename,
                media.ZIDENTIFIER AS media_uuid,
                acc.ZIDENTIFIER AS account_id,
                att.ZTYPEUTI    AS uti
            FROM ZICCLOUDSYNCINGOBJECT att
            JOIN ZICCLOUDSYNCINGOBJECT media ON media.Z_PK = att.ZMEDIA
            JOIN ZICCLOUDSYNCINGOBJECT note  ON note.Z_PK  = att.ZNOTE
            JOIN ZICCLOUDSYNCINGOBJECT acc   ON acc.Z_PK   = note.{account_col}
            WHERE att.ZTYPEUTI = 'com.adobe.pdf'
              AND note.Z_PK = ?
            """,
            (note_pk,),
        ).fetchall()

        return [
            {
                "note_title": r[0],
                "note_pk": r[1],
                "filename": r[2],
                "media_uuid": r[3],
                "account_id": r[4],
                "uti": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


def query_all_attachments(
    db_path: str,
    account_col: str,
    note_pk: int | None = None,
) -> list[dict]:
    """Query all attachments, optionally filtered to a note."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        where = "WHERE att.ZTYPEUTI IS NOT NULL"
        params: tuple = ()
        if note_pk is not None:
            where += " AND note.Z_PK = ?"
            params = (note_pk,)

        rows = conn.execute(
            f"""
            SELECT
                note.ZTITLE1      AS note_title,
                note.Z_PK         AS note_pk,
                media.ZFILENAME   AS filename,
                media.ZIDENTIFIER AS media_uuid,
                acc.ZIDENTIFIER   AS account_id,
                att.ZTYPEUTI      AS uti
            FROM ZICCLOUDSYNCINGOBJECT att
            JOIN ZICCLOUDSYNCINGOBJECT media ON media.Z_PK = att.ZMEDIA
            JOIN ZICCLOUDSYNCINGOBJECT note  ON note.Z_PK  = att.ZNOTE
            JOIN ZICCLOUDSYNCINGOBJECT acc   ON acc.Z_PK   = note.{account_col}
            {where}
            """,
            params,
        ).fetchall()

        return [
            {
                "note_title": r[0],
                "note_pk": r[1],
                "filename": r[2],
                "media_uuid": r[3],
                "account_id": r[4],
                "uti": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


def resolve_media_path(account_id: str, media_uuid: str, filename: str) -> str | None:
    """Resolve the on-disk path for a media attachment.

    The actual path has an intermediate subdirectory:
    Accounts/{account_id}/Media/{media_uuid}/{sub_uuid}/{filename}
    We glob to find the file.
    """
    pattern = os.path.join(
        MEDIA_BASE,
        "Accounts",
        account_id,
        "Media",
        media_uuid,
        "*",
        filename,
    )
    matches = glob.glob(pattern)
    return matches[0] if matches else None
```

**Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_notestore.py -v
```

**Step 5: Commit**

```bash
git add src/apple_notes_pdf_mcp/notestore.py tests/test_notestore.py
git commit -m "feat: add NoteStore SQLite query module"
```

---

### Task 4: AppleScript Module (`applescript.py`)

**Files:**
- Create: `src/apple_notes_pdf_mcp/applescript.py`
- Create: `tests/test_applescript.py`

**Step 1: Write failing tests in `tests/test_applescript.py`**

Mock `subprocess.run` to test parsing logic without requiring Notes.app.

```python
import json
from unittest.mock import patch, MagicMock
import pytest
from apple_notes_pdf_mcp.applescript import (
    list_notes,
    search_notes,
    get_note,
)


def _mock_osascript(script_output: str):
    """Helper to mock osascript returning given output."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = script_output
    mock.stderr = ""
    return patch("subprocess.run", return_value=mock)


class TestListNotes:
    def test_parses_note_list(self):
        output = json.dumps([
            {
                "id": "x-coredata://123/ICNote/p456",
                "title": "Test Note",
                "folder": "Notes",
                "snippet": "Some text here",
                "modification_date": "2026-03-10T14:22:00Z",
                "attachment_count": 1,
            }
        ])
        with _mock_osascript(output):
            notes = list_notes()
        assert len(notes) == 1
        assert notes[0]["title"] == "Test Note"
        assert notes[0]["attachment_count"] == 1

    def test_filter_by_folder(self):
        output = json.dumps([])
        with _mock_osascript(output) as mock_run:
            list_notes(folder="Work")
            call_args = mock_run.call_args[0][0]
            script = call_args[2]  # The -e argument
            assert "Work" in script


class TestSearchNotes:
    def test_search_returns_matches(self):
        output = json.dumps([
            {
                "id": "x-coredata://123/ICNote/p789",
                "title": "Meeting",
                "folder": "Work",
                "snippet": "Discuss project...",
                "modification_date": "2026-03-10T14:22:00Z",
                "attachment_count": 0,
            }
        ])
        with _mock_osascript(output):
            results = search_notes("project")
        assert len(results) == 1


class TestGetNote:
    def test_get_single_note(self):
        output = json.dumps({
            "id": "x-coredata://123/ICNote/p456",
            "title": "Test Note",
            "body": "Full body text of the note",
            "folder": "Notes",
            "modification_date": "2026-03-10T14:22:00Z",
            "attachments": [
                {"name": "doc.pdf", "type": "com.adobe.pdf"}
            ],
        })
        with _mock_osascript(output):
            note = get_note("x-coredata://123/ICNote/p456")
        assert note["body"] == "Full body text of the note"
        assert len(note["attachments"]) == 1
```

**Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_applescript.py -v
```

**Step 3: Implement `applescript.py`**

```python
"""AppleScript wrappers for Apple Notes access via osascript."""

from __future__ import annotations

import json
import subprocess


def _run_applescript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr}")
    return result.stdout.strip()


def list_notes(folder: str | None = None) -> list[dict]:
    """List all notes with basic metadata."""
    folder_filter = ""
    if folder:
        folder_filter = f'of folder "{folder}"'

    script = f'''
    tell application "Notes"
        set noteList to {{}}
        set allNotes to every note {folder_filter}
        repeat with n in allNotes
            set noteId to id of n
            set noteTitle to name of n
            set noteFolder to name of container of n
            set noteBody to plaintext of n
            set noteSnippet to text 1 thru (min of (200, length of noteBody)) of noteBody
            set modDate to modification date of n
            set attCount to count of attachments of n
            set dateStr to (year of modDate as text) & "-" & my padNum(month of modDate as integer) & "-" & my padNum(day of modDate) & "T" & my padNum(hours of modDate) & ":" & my padNum(minutes of modDate) & ":" & my padNum(seconds of modDate) & "Z"
            set end of noteList to "{{\\"id\\": \\"" & noteId & "\\", \\"title\\": \\"" & my escapeStr(noteTitle) & "\\", \\"folder\\": \\"" & my escapeStr(noteFolder) & "\\", \\"snippet\\": \\"" & my escapeStr(noteSnippet) & "\\", \\"modification_date\\": \\"" & dateStr & "\\", \\"attachment_count\\": " & attCount & "}}"
        end repeat
        return "[" & my joinList(noteList, ", ") & "]"
    end tell

    on padNum(n)
        if n < 10 then
            return "0" & (n as text)
        else
            return n as text
        end if
    end padNum

    on escapeStr(s)
        set output to ""
        repeat with c in characters of s
            if c as text is "\\"" then
                set output to output & "\\\\\\""
            else if c as text is "\\\\" then
                set output to output & "\\\\\\\\"
            else if c as text is (ASCII character 10) then
                set output to output & "\\\\n"
            else if c as text is (ASCII character 13) then
                set output to output & "\\\\n"
            else
                set output to output & (c as text)
            end if
        end repeat
        return output
    end escapeStr

    on joinList(lst, delim)
        set oldDelim to AppleScript's text item delimiters
        set AppleScript's text item delimiters to delim
        set result to lst as text
        set AppleScript's text item delimiters to oldDelim
        return result
    end joinList
    '''
    output = _run_applescript(script)
    if not output:
        return []
    return json.loads(output)


def search_notes(query: str) -> list[dict]:
    """Search notes by body text content."""
    script = f'''
    tell application "Notes"
        set noteList to {{}}
        set matchingNotes to every note whose plaintext contains "{query}"
        repeat with n in matchingNotes
            set noteId to id of n
            set noteTitle to name of n
            set noteFolder to name of container of n
            set noteBody to plaintext of n
            set noteSnippet to text 1 thru (min of (200, length of noteBody)) of noteBody
            set modDate to modification date of n
            set attCount to count of attachments of n
            set dateStr to (year of modDate as text) & "-" & my padNum(month of modDate as integer) & "-" & my padNum(day of modDate) & "T" & my padNum(hours of modDate) & ":" & my padNum(minutes of modDate) & ":" & my padNum(seconds of modDate) & "Z"
            set end of noteList to "{{\\"id\\": \\"" & noteId & "\\", \\"title\\": \\"" & my escapeStr(noteTitle) & "\\", \\"folder\\": \\"" & my escapeStr(noteFolder) & "\\", \\"snippet\\": \\"" & my escapeStr(noteSnippet) & "\\", \\"modification_date\\": \\"" & dateStr & "\\", \\"attachment_count\\": " & attCount & "}}"
        end repeat
        return "[" & my joinList(noteList, ", ") & "]"
    end tell

    on padNum(n)
        if n < 10 then
            return "0" & (n as text)
        else
            return n as text
        end if
    end padNum

    on escapeStr(s)
        set output to ""
        repeat with c in characters of s
            if c as text is "\\"" then
                set output to output & "\\\\\\""
            else if c as text is "\\\\" then
                set output to output & "\\\\\\\\"
            else if c as text is (ASCII character 10) then
                set output to output & "\\\\n"
            else if c as text is (ASCII character 13) then
                set output to output & "\\\\n"
            else
                set output to output & (c as text)
            end if
        end repeat
        return output
    end escapeStr

    on joinList(lst, delim)
        set oldDelim to AppleScript's text item delimiters
        set AppleScript's text item delimiters to delim
        set result to lst as text
        set AppleScript's text item delimiters to oldDelim
        return result
    end joinList
    '''
    output = _run_applescript(script)
    if not output:
        return []
    return json.loads(output)


def get_note(note_id: str) -> dict:
    """Get a single note's full body text and attachment metadata."""
    script = f'''
    tell application "Notes"
        set n to note id "{note_id}"
        set noteId to id of n
        set noteTitle to name of n
        set noteBody to plaintext of n
        set noteFolder to name of container of n
        set modDate to modification date of n
        set dateStr to (year of modDate as text) & "-" & my padNum(month of modDate as integer) & "-" & my padNum(day of modDate) & "T" & my padNum(hours of modDate) & ":" & my padNum(minutes of modDate) & ":" & my padNum(seconds of modDate) & "Z"

        set attList to {{}}
        repeat with a in attachments of n
            set attName to name of a
            set attType to content identifier of a
            set end of attList to "{{\\"name\\": \\"" & my escapeStr(attName) & "\\", \\"type\\": \\"" & attType & "}}"
        end repeat

        return "{{\\"id\\": \\"" & noteId & "\\", \\"title\\": \\"" & my escapeStr(noteTitle) & "\\", \\"body\\": \\"" & my escapeStr(noteBody) & "\\", \\"folder\\": \\"" & my escapeStr(noteFolder) & "\\", \\"modification_date\\": \\"" & dateStr & "\\", \\"attachments\\": [" & my joinList(attList, ", ") & "]}}"
    end tell

    on padNum(n)
        if n < 10 then
            return "0" & (n as text)
        else
            return n as text
        end if
    end padNum

    on escapeStr(s)
        set output to ""
        repeat with c in characters of s
            if c as text is "\\"" then
                set output to output & "\\\\\\""
            else if c as text is "\\\\" then
                set output to output & "\\\\\\\\"
            else if c as text is (ASCII character 10) then
                set output to output & "\\\\n"
            else if c as text is (ASCII character 13) then
                set output to output & "\\\\n"
            else
                set output to output & (c as text)
            end if
        end repeat
        return output
    end escapeStr

    on joinList(lst, delim)
        set oldDelim to AppleScript's text item delimiters
        set AppleScript's text item delimiters to delim
        set result to lst as text
        set AppleScript's text item delimiters to oldDelim
        return result
    end joinList
    '''
    output = _run_applescript(script)
    return json.loads(output)
```

**Note:** The AppleScript string escaping is complex. The actual implementation should be refined during development — the key design is: osascript produces JSON strings, Python parses them. The mock tests verify the parsing pipeline works.

**Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_applescript.py -v
```

**Step 5: Commit**

```bash
git add src/apple_notes_pdf_mcp/applescript.py tests/test_applescript.py
git commit -m "feat: add AppleScript wrappers for Notes.app access"
```

---

### Task 5: MCP Server (`server.py`)

**Files:**
- Create: `src/apple_notes_pdf_mcp/server.py`

**Step 1: Implement the MCP server with all 5 tools**

```python
"""MCP server entry point with tool definitions."""

from __future__ import annotations

import json
import os
import logging

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
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    logger.info("Using account column: %s", _account_col)


def _get_db_copy() -> tuple[str, str]:
    """Get a temp copy of the DB for querying."""
    _init_db()
    return notestore._copy_db_to_temp(_db_path)


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
    import shutil

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
            # Get PDF attachments from SQLite
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
    import shutil

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
```

**Step 2: Commit**

```bash
git add src/apple_notes_pdf_mcp/server.py
git commit -m "feat: add MCP server with all 5 tools"
```

---

### Task 6: Integration Smoke Test

**Step 1: Run the server locally to verify it starts**

```bash
cd /Users/jamesalexander/Developer/apple-notes-pdf-mcp
uv run apple-notes-pdf-mcp
# Should start and listen on stdio — Ctrl-C to stop
```

**Step 2: Run all unit tests**

```bash
uv run pytest tests/ -v
```

**Step 3: Final commit with any fixes**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```

---

### Task 7: CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

Add project-specific instructions for future Claude sessions working on this codebase.

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with project conventions"
```
