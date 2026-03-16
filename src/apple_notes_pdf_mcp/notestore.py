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
