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
