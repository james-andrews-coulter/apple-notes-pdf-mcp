import sqlite3
import pytest
from apple_notes_pdf_mcp.notestore import (
    find_account_column,
    query_pdf_attachments,
    query_all_attachments,
    search_notes,
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
    # Insert note (Z_PK=2, ZACCOUNT4=1) — title has "Test", snippet has "blood"
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZSNIPPET, ZMODIFICATIONDATE1, ZACCOUNT4)
        VALUES (2, 'Test Note', 'Some snippet about blood work', 700000000.0, 1)
    """)
    # Insert a second note (Z_PK=7) — title is generic, but has PDF with specific name
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZSNIPPET, ZMODIFICATIONDATE1, ZACCOUNT4)
        VALUES (7, 'Followup appointment', NULL, 700100000.0, 1)
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
    assert len(results) == 3  # doc.pdf, photo.jpg, ferritin blood test results.pdf
    types = {r["uti"] for r in results}
    assert "com.adobe.pdf" in types
    assert "public.jpeg" in types


def test_query_all_attachments_filtered(notestore_db):
    results = query_all_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    assert len(results) == 2


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
