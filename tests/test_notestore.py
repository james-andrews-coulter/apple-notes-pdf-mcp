import sqlite3
import pytest
from apple_notes_pdf_mcp.notestore import (
    _create_fts_index,
    find_account_column,
    get_note_identifier,
    list_folders,
    list_notes_sql,
    query_image_attachments,
    query_pdf_attachments,
    query_all_attachments,
    search_notes,
    search_notes_fts,
)


@pytest.fixture
def notestore_db(tmp_path):
    """Create a minimal NoteStore.sqlite fixture with Z_METADATA."""
    db_path = tmp_path / "NoteStore.sqlite"
    conn = sqlite3.connect(str(db_path))

    # Z_METADATA stores the Core Data store UUID
    conn.execute("""
        CREATE TABLE Z_METADATA (
            Z_VERSION INTEGER,
            Z_UUID VARCHAR,
            Z_PLIST BLOB
        )
    """)
    conn.execute("""
        INSERT INTO Z_METADATA (Z_VERSION, Z_UUID)
        VALUES (1, 'TEST-STORE-UUID')
    """)

    conn.execute("""
        CREATE TABLE ZICCLOUDSYNCINGOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            Z_ENT INTEGER,
            ZTITLE1 TEXT,
            ZSNIPPET TEXT,
            ZMODIFICATIONDATE1 FLOAT,
            ZCREATIONDATE3 FLOAT,
            ZMEDIA INTEGER,
            ZNOTE INTEGER,
            ZFILENAME TEXT,
            ZIDENTIFIER TEXT,
            ZTYPEUTI TEXT,
            ZACCOUNT4 INTEGER,
            ZTITLE2 TEXT,
            ZPARENT INTEGER,
            ZFOLDER INTEGER,
            ZSUMMARY TEXT,
            ZOCRSUMMARY TEXT,
            ZURLSTRING TEXT
        )
    """)
    # Insert account (Z_PK=1)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZIDENTIFIER)
        VALUES (1, 'LocalAccount')
    """)
    # Insert folders
    # Root folder (PK=100)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE2) VALUES (100, 'Health & Fitness')
    """)
    # Subfolder (PK=101, parent=100)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE2, ZPARENT) VALUES (101, 'Lab Results', 100)
    """)
    # Another root folder (PK=102)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE2) VALUES (102, 'Work')
    """)

    # Insert note (Z_PK=2, ZACCOUNT4=1) — title has "Test", snippet has "blood", in Work folder
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZSNIPPET, ZMODIFICATIONDATE1, ZCREATIONDATE3, ZACCOUNT4, ZIDENTIFIER, ZFOLDER)
        VALUES (2, 'Test Note', 'Some snippet about blood work', 700000000.0, 699900000.0, 1, 'NOTE-UUID-2', 102)
    """)
    # Insert a second note (Z_PK=7) — title is generic, but has PDF with specific name, in Lab Results subfolder
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZSNIPPET, ZMODIFICATIONDATE1, ZCREATIONDATE3, ZACCOUNT4, ZIDENTIFIER, ZFOLDER)
        VALUES (7, 'Followup appointment', NULL, 700100000.0, 700050000.0, 1, 'NOTE-UUID-7', 101)
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
    # Insert non-PDF media (Z_PK=6)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER)
        VALUES (6, 'photo.jpg', 'MEDIA-UUID-456')
    """)
    # Insert non-PDF attachment (Z_PK=5, ZMEDIA=6, ZNOTE=2)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI)
        VALUES (5, 6, 2, 'public.jpeg')
    """)
    # Insert media for note 7 — PDF with "ferritin" in filename
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER)
        VALUES (8, 'ferritin blood test results.pdf', 'MEDIA-UUID-789')
    """)
    # Insert attachment linking media 8 to note 7
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI)
        VALUES (9, 8, 7, 'com.adobe.pdf')
    """)
    # Insert a URL row linked to note 7 (for testing FTS5 url indexing)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZNOTE, ZURLSTRING)
        VALUES (10, 7, 'https://example.com/lab-results')
    """)
    # Insert image media (Z_PK=11)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER)
        VALUES (11, 'screenshot.png', 'MEDIA-UUID-IMG')
    """)
    # Insert image attachment (Z_PK=12, ZMEDIA=11, ZNOTE=2)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI)
        VALUES (12, 11, 2, 'public.png')
    """)
    # Add a summary to note 2 for testing FTS5 summary indexing
    conn.execute("""
        UPDATE ZICCLOUDSYNCINGOBJECT SET ZSUMMARY = 'Annual checkup notes'
        WHERE Z_PK = 2
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
    assert len(results) == 4  # doc.pdf, photo.jpg, ferritin blood test results.pdf, screenshot.png
    types = {r["uti"] for r in results}
    assert "com.adobe.pdf" in types
    assert "public.jpeg" in types


def test_query_all_attachments_filtered(notestore_db):
    results = query_all_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    assert len(results) == 3  # doc.pdf, photo.jpg, screenshot.png


def test_query_image_attachments(notestore_db):
    """Image query returns only image attachments, not PDFs."""
    results = query_image_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    assert len(results) == 2  # photo.jpg (public.jpeg) and screenshot.png (public.png)
    utis = {r["uti"] for r in results}
    assert "public.jpeg" in utis
    assert "public.png" in utis
    assert "com.adobe.pdf" not in utis

    # Note 7 has no image attachments
    results = query_image_attachments(notestore_db, "ZACCOUNT4", note_pk=7)
    assert results == []


class TestSearchNotes:
    def test_search_by_title(self, notestore_db):
        """Search term in note title should find the note."""
        results = search_notes(notestore_db, "ZACCOUNT4", "Test")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        assert "Test Note" in titles

    def test_search_by_snippet(self, notestore_db):
        """Search term in snippet should find the note."""
        results = search_notes(notestore_db, "ZACCOUNT4", "blood")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        assert "Test Note" in titles

    def test_search_by_attachment_filename(self, notestore_db):
        """Search term only in attachment filename should still find the parent note."""
        results = search_notes(notestore_db, "ZACCOUNT4", "ferritin")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        # "ferritin" is NOT in the note title "Followup appointment"
        # but IS in the attachment filename — search must find it
        assert "Followup appointment" in titles

    def test_search_no_match(self, notestore_db):
        results = search_notes(notestore_db, "ZACCOUNT4", "xyznonexistent")
        assert results == []

    def test_search_deduplicates(self, notestore_db):
        """A note matching both title and attachment should appear once."""
        results = search_notes(notestore_db, "ZACCOUNT4", "Test")
        pks = [r["id"] for r in results]
        assert len(pks) == len(set(pks))

    def test_search_returns_valid_note_id(self, notestore_db):
        """Note IDs should be valid x-coredata:// format."""
        results = search_notes(notestore_db, "ZACCOUNT4", "Test")
        assert len(results) >= 1
        assert results[0]["id"].startswith("x-coredata://")
        assert "/ICNote/p" in results[0]["id"]

    def test_search_includes_attachment_count(self, notestore_db):
        """Results should include attachment_count."""
        results = search_notes(notestore_db, "ZACCOUNT4", "ferritin")
        note = [r for r in results if r["title"] == "Followup appointment"][0]
        assert note["attachment_count"] == 1

    def test_search_includes_note_url(self, notestore_db):
        """Search results should include note_url with deep link."""
        results = search_notes(notestore_db, "ZACCOUNT4", "Test")
        assert len(results) >= 1
        note = [r for r in results if r["title"] == "Test Note"][0]
        assert note["note_url"] == "applenotes://showNote?noteId=NOTE-UUID-2"


def test_get_note_identifier(notestore_db):
    """get_note_identifier returns the correct ZIDENTIFIER for a known PK."""
    assert get_note_identifier(notestore_db, 2) == "NOTE-UUID-2"
    assert get_note_identifier(notestore_db, 7) == "NOTE-UUID-7"
    assert get_note_identifier(notestore_db, 999) is None


class TestListFolders:
    def test_list_folders(self, notestore_db):
        """Returns all folders with correct hierarchy, depth, and note counts."""
        folders = list_folders(notestore_db)
        assert len(folders) == 3

        by_name = {f["name"]: f for f in folders}

        # Root folders
        hf = by_name["Health & Fitness"]
        assert hf["depth"] == 0
        assert hf["parent_pk"] is None
        assert hf["note_count"] == 0  # no notes directly in this folder

        work = by_name["Work"]
        assert work["depth"] == 0
        assert work["parent_pk"] is None
        assert work["note_count"] == 1  # "Test Note"

        # Subfolder
        lab = by_name["Lab Results"]
        assert lab["depth"] == 1
        assert lab["parent_pk"] == 100
        assert lab["note_count"] == 1  # "Followup appointment"


class TestFolderScopedSearch:
    def test_search_with_folder_scope(self, notestore_db):
        """Searching with folder_name should find notes in subfolders."""
        results = search_notes(notestore_db, "ZACCOUNT4", "ferritin", folder_name="Health & Fitness")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        assert "Followup appointment" in titles

    def test_search_with_folder_excludes_other(self, notestore_db):
        """Searching with folder_name should NOT find notes in other folders."""
        results = search_notes(notestore_db, "ZACCOUNT4", "Test", folder_name="Health & Fitness")
        titles = {r["title"] for r in results}
        assert "Test Note" not in titles

    def test_search_with_nonexistent_folder(self, notestore_db):
        """Searching with a nonexistent folder returns empty results."""
        results = search_notes(notestore_db, "ZACCOUNT4", "Test", folder_name="Nonexistent Folder")
        assert results == []


class TestListNotesSql:
    def test_list_notes_sql_default(self, notestore_db):
        """Returns notes sorted by modification date desc with all expected fields."""
        results = list_notes_sql(notestore_db, "ZACCOUNT4")
        assert len(results) == 2
        # Most recently modified first (700100000 > 700000000)
        assert results[0]["title"] == "Followup appointment"
        assert results[1]["title"] == "Test Note"
        # Check all expected fields present
        for note in results:
            assert "id" in note
            assert "title" in note
            assert "folder" in note
            assert "snippet" in note
            assert "modification_date" in note
            assert "attachment_count" in note
            assert "note_url" in note
            assert note["id"].startswith("x-coredata://")

    def test_list_notes_sql_ascending(self, notestore_db):
        """ascending=True returns oldest-modified first."""
        results = list_notes_sql(notestore_db, "ZACCOUNT4", ascending=True)
        assert len(results) == 2
        # Oldest first (700000000 < 700100000)
        assert results[0]["title"] == "Test Note"
        assert results[1]["title"] == "Followup appointment"

    def test_list_notes_sql_limit(self, notestore_db):
        """limit=1 returns only 1 note."""
        results = list_notes_sql(notestore_db, "ZACCOUNT4", limit=1)
        assert len(results) == 1

    def test_list_notes_sql_folder(self, notestore_db):
        """folder_name scopes results to that folder and subfolders."""
        results = list_notes_sql(notestore_db, "ZACCOUNT4", folder_name="Health & Fitness")
        assert len(results) == 1
        assert results[0]["title"] == "Followup appointment"

        # Work folder should only have Test Note
        results = list_notes_sql(notestore_db, "ZACCOUNT4", folder_name="Work")
        assert len(results) == 1
        assert results[0]["title"] == "Test Note"

    def test_list_notes_sql_includes_note_url(self, notestore_db):
        """Results include note_url field with deep link."""
        results = list_notes_sql(notestore_db, "ZACCOUNT4")
        by_title = {r["title"]: r for r in results}
        assert by_title["Test Note"]["note_url"] == "applenotes://showNote?noteId=NOTE-UUID-2"
        assert by_title["Followup appointment"]["note_url"] == "applenotes://showNote?noteId=NOTE-UUID-7"


class TestFTS5Search:
    def test_create_fts_index(self, notestore_db):
        """_create_fts_index creates a queryable FTS5 table."""
        _create_fts_index(notestore_db)
        conn = sqlite3.connect(notestore_db)
        try:
            # Content-less FTS5 table: verify it exists and has indexed rows
            # by checking that a known term matches
            rows = conn.execute(
                "SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?", ("Test",)
            ).fetchall()
            assert len(rows) >= 1
            rows = conn.execute(
                "SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?", ("Followup",)
            ).fetchall()
            assert len(rows) >= 1
        finally:
            conn.close()

    def test_fts_search_by_title(self, notestore_db):
        """FTS5 search finds notes by title."""
        results = search_notes_fts(notestore_db, "ZACCOUNT4", "Test")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        assert "Test Note" in titles
        assert results[0]["match_surface"] == "fts5"

    def test_fts_search_by_filename(self, notestore_db):
        """FTS5 search finds notes via attachment filename."""
        results = search_notes_fts(notestore_db, "ZACCOUNT4", "ferritin")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        assert "Followup appointment" in titles

    def test_fts_search_with_folder(self, notestore_db):
        """FTS5 search with folder_name scopes results to folder subtree."""
        # "ferritin" is in Lab Results (subfolder of Health & Fitness)
        results = search_notes_fts(notestore_db, "ZACCOUNT4", "ferritin", folder_name="Health & Fitness")
        assert len(results) >= 1
        titles = {r["title"] for r in results}
        assert "Followup appointment" in titles

        # "Test" note is in Work folder, should NOT appear in Health & Fitness scope
        results = search_notes_fts(notestore_db, "ZACCOUNT4", "Test", folder_name="Health & Fitness")
        titles = {r["title"] for r in results}
        assert "Test Note" not in titles

    def test_fts_search_no_match(self, notestore_db):
        """FTS5 search returns empty for nonsense query."""
        results = search_notes_fts(notestore_db, "ZACCOUNT4", "xyznonexistent")
        assert results == []

    def test_fts_prefix_match(self, notestore_db):
        """FTS5 prefix search with * finds partial matches."""
        _create_fts_index(notestore_db)
        conn = sqlite3.connect(f"file:{notestore_db}?mode=ro", uri=True)
        try:
            # Direct FTS5 prefix query
            rows = conn.execute(
                "SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?",
                ("ferr*",),
            ).fetchall()
            assert len(rows) >= 1
        finally:
            conn.close()
