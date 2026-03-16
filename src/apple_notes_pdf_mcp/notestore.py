"""SQLite queries against Apple Notes NoteStore.sqlite."""

from __future__ import annotations

import datetime
import glob
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager


NOTESTORE_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
)

MEDIA_BASE = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.notes"
)

_ATTACHMENT_QUERY = """
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
"""


@contextmanager
def open_notestore(db_path: str):
    """Copy NoteStore DB to temp dir and yield the path. Cleans up on exit."""
    tmp_dir = tempfile.mkdtemp(prefix="notes_mcp_")
    dest = os.path.join(tmp_dir, "NoteStore.sqlite")
    shutil.copy2(db_path, dest)
    for suffix in ("-wal", "-shm"):
        src = db_path + suffix
        if os.path.exists(src):
            shutil.copy2(src, dest + suffix)
    try:
        yield dest
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _copy_db_to_temp(db_path: str) -> tuple[str, str]:
    """Copy DB and WAL to temp dir to avoid lock contention.

    Deprecated: prefer using open_notestore() context manager instead.
    """
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


def _validate_account_col(account_col: str) -> None:
    """Validate that account_col is a safe ZACCOUNT column name."""
    if not (account_col.startswith("ZACCOUNT") and account_col[8:].isdigit()):
        raise ValueError(f"Invalid account column: {account_col}")


def _attachment_row_to_dict(row) -> dict:
    """Convert a row from the attachment query to a dict."""
    return {
        "note_title": row[0],
        "note_pk": row[1],
        "filename": row[2],
        "media_uuid": row[3],
        "account_id": row[4],
        "uti": row[5],
    }


def get_store_uuid(db_path: str) -> str | None:
    """Get the Core Data store UUID from Z_METADATA."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT Z_UUID FROM Z_METADATA LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def find_account_column(db_path: str) -> str:
    """Probe ZICCLOUDSYNCINGOBJECT to find the correct ZACCOUNT column.

    The column used for note->account joins varies by macOS version.
    We try ZACCOUNT columns with numeric suffixes and find which one
    produces valid join results (notes with titles joined to accounts with identifiers).
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
    _validate_account_col(account_col)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            _ATTACHMENT_QUERY.format(account_col=account_col)
            + """
            WHERE att.ZTYPEUTI = 'com.adobe.pdf'
              AND note.Z_PK = ?
            """,
            (note_pk,),
        ).fetchall()

        return [_attachment_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def query_all_attachments(
    db_path: str,
    account_col: str,
    note_pk: int | None = None,
) -> list[dict]:
    """Query all attachments, optionally filtered to a note."""
    _validate_account_col(account_col)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        where = "WHERE att.ZTYPEUTI IS NOT NULL"
        params: tuple = ()
        if note_pk is not None:
            where += " AND note.Z_PK = ?"
            params = (note_pk,)

        rows = conn.execute(
            _ATTACHMENT_QUERY.format(account_col=account_col) + where,
            params,
        ).fetchall()

        return [_attachment_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def search_notes(
    db_path: str,
    account_col: str,
    query: str,
) -> list[dict]:
    """Multi-surface search across note titles, snippets, and attachment filenames.

    This is far more powerful than AppleScript search which can only hit body
    plaintext. This searches ZTITLE1 (note title), ZSNIPPET (body preview),
    and ZFILENAME (attachment filenames) — finding notes where the search term
    appears in any of these surfaces.
    """
    _validate_account_col(account_col)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        like_query = f"%{query}%"

        # Search note titles and snippets directly
        title_hits = conn.execute(
            f"""
            SELECT DISTINCT
                note.Z_PK          AS note_pk,
                note.ZTITLE1       AS title,
                note.ZSNIPPET      AS snippet,
                note.ZMODIFICATIONDATE1 AS mod_date
            FROM ZICCLOUDSYNCINGOBJECT note
            WHERE note.ZTITLE1 IS NOT NULL
              AND (
                  note.ZTITLE1 LIKE ? COLLATE NOCASE
                  OR note.ZSNIPPET LIKE ? COLLATE NOCASE
              )
            """,
            (like_query, like_query),
        ).fetchall()

        # Search attachment filenames and resolve back to parent notes
        attachment_hits = conn.execute(
            f"""
            SELECT DISTINCT
                note.Z_PK          AS note_pk,
                note.ZTITLE1       AS title,
                note.ZSNIPPET      AS snippet,
                note.ZMODIFICATIONDATE1 AS mod_date
            FROM ZICCLOUDSYNCINGOBJECT media
            JOIN ZICCLOUDSYNCINGOBJECT att  ON att.ZMEDIA = media.Z_PK
            JOIN ZICCLOUDSYNCINGOBJECT note ON note.Z_PK  = att.ZNOTE
            WHERE media.ZFILENAME LIKE ? COLLATE NOCASE
              AND note.ZTITLE1 IS NOT NULL
            """,
            (like_query,),
        ).fetchall()

        # Build set of title-hit PKs for O(1) lookup
        title_pks = {r[0] for r in title_hits}

        # Get store UUID once before the loop
        store_uuid = get_store_uuid(db_path)
        uuid_part = store_uuid if store_uuid else "unknown"

        # Deduplicate and build results
        seen = set()
        results = []
        for r in [*title_hits, *attachment_hits]:
            if r[0] in seen:
                continue
            seen.add(r[0])

            # Count attachments for this note
            att_count = conn.execute(
                "SELECT COUNT(*) FROM ZICCLOUDSYNCINGOBJECT WHERE ZNOTE = ? AND ZTYPEUTI IS NOT NULL",
                (r[0],),
            ).fetchone()[0]

            # Convert Core Data timestamp to ISO (Core Data epoch is 2001-01-01)
            mod_date_str = None
            if r[3] is not None:
                cd_epoch = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
                mod_date = cd_epoch + datetime.timedelta(seconds=r[3])
                mod_date_str = mod_date.isoformat()

            # Build the x-coredata ID using real store UUID
            note_id = f"x-coredata://{uuid_part}/ICNote/p{r[0]}"

            results.append({
                "id": note_id,
                "title": r[1] or "",
                "snippet": (r[2] or "")[:200],
                "modification_date": mod_date_str,
                "attachment_count": att_count,
                "match_surface": "title/snippet" if r[0] in title_pks else "attachment_filename",
            })

        return results
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
