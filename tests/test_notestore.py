import sqlite3
import pytest
from apple_notes_pdf_mcp.notestore import (
    find_account_column,
    list_folders,
    list_notes_sql,
    query_pdf_attachments,
    query_image_attachments,
    search_notes,
    search_notes_fts,
)


@pytest.fixture
def notestore_db(tmp_path):
    """Minimal NoteStore.sqlite fixture with notes, attachments, and folders."""
    db_path = tmp_path / "NoteStore.sqlite"
    conn = sqlite3.connect(str(db_path))

    conn.execute("""
        CREATE TABLE Z_METADATA (Z_VERSION INTEGER, Z_UUID VARCHAR, Z_PLIST BLOB)
    """)
    conn.execute("INSERT INTO Z_METADATA (Z_VERSION, Z_UUID) VALUES (1, 'TEST-STORE-UUID')")

    conn.execute("""
        CREATE TABLE ZICCLOUDSYNCINGOBJECT (
            Z_PK INTEGER PRIMARY KEY, Z_ENT INTEGER,
            ZTITLE1 TEXT, ZSNIPPET TEXT, ZMODIFICATIONDATE1 FLOAT,
            ZCREATIONDATE3 FLOAT, ZMEDIA INTEGER, ZNOTE INTEGER,
            ZFILENAME TEXT, ZIDENTIFIER TEXT, ZTYPEUTI TEXT,
            ZACCOUNT4 INTEGER, ZTITLE2 TEXT, ZPARENT INTEGER,
            ZFOLDER INTEGER, ZSUMMARY TEXT, ZOCRSUMMARY TEXT, ZURLSTRING TEXT
        )
    """)

    # Account
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZIDENTIFIER) VALUES (1, 'LocalAccount')")

    # Folders: Health & Fitness (100) → Lab Results (101), Work (102)
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE2) VALUES (100, 'Health & Fitness')")
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE2, ZPARENT) VALUES (101, 'Lab Results', 100)")
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE2) VALUES (102, 'Work')")

    # Note 2: "Test Note" in Work, has PDF + JPEG + PNG attachments
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZSNIPPET, ZMODIFICATIONDATE1, ZCREATIONDATE3, ZACCOUNT4, ZIDENTIFIER, ZFOLDER, ZSUMMARY)
        VALUES (2, 'Test Note', 'Some snippet about blood work', 700000000.0, 699900000.0, 1, 'NOTE-UUID-2', 102, 'Annual checkup notes')
    """)
    # Note 7: "Followup appointment" in Lab Results (subfolder of Health & Fitness)
    conn.execute("""
        INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZTITLE1, ZMODIFICATIONDATE1, ZCREATIONDATE3, ZACCOUNT4, ZIDENTIFIER, ZFOLDER)
        VALUES (7, 'Followup appointment', 700100000.0, 700050000.0, 1, 'NOTE-UUID-7', 101)
    """)

    # PDF attachment on note 2
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER) VALUES (3, 'doc.pdf', 'MEDIA-UUID-123')")
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI) VALUES (4, 3, 2, 'com.adobe.pdf')")
    # JPEG attachment on note 2
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER) VALUES (6, 'photo.jpg', 'MEDIA-UUID-456')")
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI) VALUES (5, 6, 2, 'public.jpeg')")
    # PNG attachment on note 2
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER) VALUES (11, 'screenshot.png', 'MEDIA-UUID-IMG')")
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI) VALUES (12, 11, 2, 'public.png')")
    # PDF attachment on note 7 with "ferritin" in filename
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZFILENAME, ZIDENTIFIER) VALUES (8, 'ferritin blood test results.pdf', 'MEDIA-UUID-789')")
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT (Z_PK, ZMEDIA, ZNOTE, ZTYPEUTI) VALUES (9, 8, 7, 'com.adobe.pdf')")

    conn.commit()
    conn.close()
    return str(db_path)


def test_find_account_column(notestore_db):
    assert find_account_column(notestore_db) == "ZACCOUNT4"


def test_query_pdf_attachments(notestore_db):
    results = query_pdf_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    assert len(results) == 1
    assert results[0]["filename"] == "doc.pdf"
    assert results[0]["account_id"] == "LocalAccount"


def test_query_image_attachments(notestore_db):
    results = query_image_attachments(notestore_db, "ZACCOUNT4", note_pk=2)
    utis = {r["uti"] for r in results}
    assert utis == {"public.jpeg", "public.png"}
    assert query_image_attachments(notestore_db, "ZACCOUNT4", note_pk=7) == []


def test_search_finds_by_title(notestore_db):
    results = search_notes(notestore_db, "ZACCOUNT4", "Test")
    assert any(r["title"] == "Test Note" for r in results)


def test_search_finds_by_attachment_filename(notestore_db):
    """The key differentiator: finds notes via attachment filename."""
    results = search_notes(notestore_db, "ZACCOUNT4", "ferritin")
    assert any(r["title"] == "Followup appointment" for r in results)


def test_search_includes_citation(notestore_db):
    results = search_notes(notestore_db, "ZACCOUNT4", "Test")
    note = [r for r in results if r["title"] == "Test Note"][0]
    assert "note_url" in note
    assert "citation" in note
    assert note["citation"].startswith("[Test Note](https://")


def test_search_with_folder_scope(notestore_db):
    # Scoped to Health & Fitness finds note in subfolder Lab Results
    results = search_notes(notestore_db, "ZACCOUNT4", "ferritin", folder_name="Health & Fitness")
    assert any(r["title"] == "Followup appointment" for r in results)


def test_search_folder_excludes_other_folders(notestore_db):
    results = search_notes(notestore_db, "ZACCOUNT4", "Test", folder_name="Health & Fitness")
    assert not any(r["title"] == "Test Note" for r in results)


def test_list_folders(notestore_db):
    folders = list_folders(notestore_db)
    by_name = {f["name"]: f for f in folders}
    assert by_name["Health & Fitness"]["depth"] == 0
    assert by_name["Lab Results"]["depth"] == 1
    assert by_name["Lab Results"]["parent_pk"] == 100
    assert by_name["Work"]["note_count"] == 1


def test_list_notes_default_sort(notestore_db):
    results = list_notes_sql(notestore_db, "ZACCOUNT4")
    assert results[0]["title"] == "Followup appointment"  # newer
    assert results[1]["title"] == "Test Note"


def test_list_notes_ascending(notestore_db):
    results = list_notes_sql(notestore_db, "ZACCOUNT4", ascending=True)
    assert results[0]["title"] == "Test Note"  # older first


def test_fts5_search(notestore_db):
    results = search_notes_fts(notestore_db, "ZACCOUNT4", "Test")
    assert any(r["title"] == "Test Note" for r in results)
    assert results[0]["match_surface"] == "fts5"


def test_fts5_prefix_match(notestore_db):
    results = search_notes_fts(notestore_db, "ZACCOUNT4", "ferr*")
    assert any(r["title"] == "Followup appointment" for r in results)
