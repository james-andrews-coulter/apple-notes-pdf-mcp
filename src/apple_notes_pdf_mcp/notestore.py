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

IMAGE_UTIS = {"public.jpeg", "public.png", "public.heic"}

_ATTACHMENT_QUERY = """
    SELECT
        note.ZTITLE1      AS note_title,
        note.Z_PK         AS note_pk,
        media.ZFILENAME   AS filename,
        media.ZIDENTIFIER AS media_uuid,
        acc.ZIDENTIFIER   AS account_id,
        att.ZTYPEUTI      AS uti,
        note.ZIDENTIFIER  AS note_identifier
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
        "note_identifier": row[6],
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


def query_image_attachments(
    db_path: str,
    account_col: str,
    note_pk: int,
) -> list[dict]:
    """Query image attachments for a specific note."""
    _validate_account_col(account_col)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        placeholders = ",".join("?" * len(IMAGE_UTIS))
        rows = conn.execute(
            _ATTACHMENT_QUERY.format(account_col=account_col)
            + f"""
            WHERE att.ZTYPEUTI IN ({placeholders})
              AND note.Z_PK = ?
            """,
            (*IMAGE_UTIS, note_pk),
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


def list_folders(db_path: str) -> list[dict]:
    """List all Apple Notes folders with hierarchy info and note counts."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("""
            WITH RECURSIVE folder_tree(pk, title, parent_pk, depth) AS (
                SELECT Z_PK, ZTITLE2, ZPARENT, 0
                FROM ZICCLOUDSYNCINGOBJECT WHERE ZTITLE2 IS NOT NULL AND ZPARENT IS NULL
                UNION ALL
                SELECT c.Z_PK, c.ZTITLE2, c.ZPARENT, ft.depth + 1
                FROM ZICCLOUDSYNCINGOBJECT c JOIN folder_tree ft ON c.ZPARENT = ft.pk
                WHERE c.ZTITLE2 IS NOT NULL
            )
            SELECT pk, title, parent_pk, depth,
                (SELECT COUNT(*) FROM ZICCLOUDSYNCINGOBJECT WHERE ZFOLDER = pk AND ZTITLE1 IS NOT NULL) AS note_count
            FROM folder_tree ORDER BY depth, title
        """).fetchall()
        return [
            {"name": r[1], "pk": r[0], "parent_pk": r[2], "depth": r[3], "note_count": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def _folder_subtree_cte(folder_name: str) -> tuple[str, tuple]:
    """Return a recursive CTE SQL fragment and params for scoping queries to a folder + descendants."""
    cte = """
        WITH RECURSIVE subtree(pk) AS (
            SELECT Z_PK FROM ZICCLOUDSYNCINGOBJECT WHERE ZTITLE2 = ?
            UNION ALL
            SELECT c.Z_PK FROM ZICCLOUDSYNCINGOBJECT c JOIN subtree s ON c.ZPARENT = s.pk
        )
    """
    return cte, (folder_name,)


def search_notes(
    db_path: str,
    account_col: str,
    query: str,
    folder_name: str | None = None,
    limit: int = 50,
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

        # Build folder scoping CTE and clause if needed
        cte_sql = ""
        cte_params: tuple = ()
        folder_clause = ""
        if folder_name is not None:
            cte_sql, cte_params = _folder_subtree_cte(folder_name)
            folder_clause = " AND note.ZFOLDER IN (SELECT pk FROM subtree)"

        # Search note titles and snippets directly
        title_hits = conn.execute(
            cte_sql + f"""
            SELECT DISTINCT
                note.Z_PK          AS note_pk,
                note.ZTITLE1       AS title,
                note.ZSNIPPET      AS snippet,
                note.ZMODIFICATIONDATE1 AS mod_date,
                note.ZIDENTIFIER   AS identifier
            FROM ZICCLOUDSYNCINGOBJECT note
            WHERE note.ZTITLE1 IS NOT NULL
              AND (
                  note.ZTITLE1 LIKE ? COLLATE NOCASE
                  OR note.ZSNIPPET LIKE ? COLLATE NOCASE
              )
            """ + folder_clause,
            cte_params + (like_query, like_query),
        ).fetchall()

        # Search attachment filenames and resolve back to parent notes
        attachment_hits = conn.execute(
            cte_sql + f"""
            SELECT DISTINCT
                note.Z_PK          AS note_pk,
                note.ZTITLE1       AS title,
                note.ZSNIPPET      AS snippet,
                note.ZMODIFICATIONDATE1 AS mod_date,
                note.ZIDENTIFIER   AS identifier
            FROM ZICCLOUDSYNCINGOBJECT media
            JOIN ZICCLOUDSYNCINGOBJECT att  ON att.ZMEDIA = media.Z_PK
            JOIN ZICCLOUDSYNCINGOBJECT note ON note.Z_PK  = att.ZNOTE
            WHERE media.ZFILENAME LIKE ? COLLATE NOCASE
              AND note.ZTITLE1 IS NOT NULL
            """ + folder_clause,
            cte_params + (like_query,),
        ).fetchall()

        # Build set of title-hit PKs for O(1) lookup
        title_pks = {r[0] for r in title_hits}

        # Get store UUID once before the loop
        store_uuid = get_store_uuid(db_path)
        uuid_part = store_uuid if store_uuid else "unknown"

        # Deduplicate and build results (respecting limit)
        seen = set()
        results = []
        for r in [*title_hits, *attachment_hits]:
            if r[0] in seen:
                continue
            if len(results) >= limit:
                break
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

            # Build deep link URL from ZIDENTIFIER
            identifier = r[4]
            note_url = f"https://james-andrews-coulter.github.io/notes-link/?id={identifier}" if identifier else None

            title = r[1] or ""
            citation = f"[{title}]({note_url})" if note_url else title

            results.append({
                "id": note_id,
                "title": title,
                "snippet": (r[2] or "")[:200],
                "modification_date": mod_date_str,
                "attachment_count": att_count,
                "match_surface": "title/snippet" if r[0] in title_pks else "attachment_filename",
                "note_url": note_url,
                "citation": citation,
            })

        return results
    finally:
        conn.close()


def list_notes_sql(
    db_path: str,
    account_col: str,
    sort_by: str = "modified",
    limit: int = 50,
    folder_name: str | None = None,
    ascending: bool = False,
) -> list[dict]:
    """List notes via SQLite with sorting and limit support.

    Args:
        db_path: Path to the (copied) NoteStore.sqlite.
        account_col: The ZACCOUNT column name for this macOS version.
        sort_by: Sort order — "modified" (default).
        limit: Maximum number of notes to return.
        folder_name: Optional folder name to scope results (includes subfolders).
        ascending: If True, sort oldest first. Default False (newest first).

    Returns:
        List of note dicts with id, title, folder, snippet,
        modification_date, attachment_count, and note_url.
    """
    _validate_account_col(account_col)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # Build folder scoping CTE and clause if needed
        cte_sql = ""
        cte_params: tuple = ()
        folder_clause = ""
        if folder_name is not None:
            cte_sql, cte_params = _folder_subtree_cte(folder_name)
            folder_clause = " AND note.ZFOLDER IN (SELECT pk FROM subtree)"

        # Sort direction
        direction = "ASC" if ascending else "DESC"
        order_clause = f"note.ZMODIFICATIONDATE1 {direction} NULLS LAST"

        sql = cte_sql + f"""
            SELECT
                note.Z_PK,
                note.ZTITLE1,
                note.ZSNIPPET,
                note.ZMODIFICATIONDATE1,
                note.ZCREATIONDATE3,
                note.ZIDENTIFIER,
                folder.ZTITLE2 AS folder_name,
                (SELECT COUNT(*) FROM ZICCLOUDSYNCINGOBJECT
                 WHERE ZNOTE = note.Z_PK AND ZTYPEUTI IS NOT NULL) AS attachment_count
            FROM ZICCLOUDSYNCINGOBJECT note
            LEFT JOIN ZICCLOUDSYNCINGOBJECT folder ON folder.Z_PK = note.ZFOLDER
            WHERE note.ZTITLE1 IS NOT NULL
            {folder_clause}
            ORDER BY {order_clause}
            LIMIT ?
        """
        params = cte_params + (limit,)
        rows = conn.execute(sql, params).fetchall()

        store_uuid = get_store_uuid(db_path)
        uuid_part = store_uuid if store_uuid else "unknown"

        results = []
        for r in rows:
            pk, title, snippet, mod_date, create_date, identifier, folder, att_count = r

            # Convert Core Data timestamp to ISO (epoch is 2001-01-01)
            mod_date_str = None
            if mod_date is not None:
                cd_epoch = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
                mod_date_str = (cd_epoch + datetime.timedelta(seconds=mod_date)).isoformat()

            note_id = f"x-coredata://{uuid_part}/ICNote/p{pk}"
            note_url = f"https://james-andrews-coulter.github.io/notes-link/?id={identifier}" if identifier else None

            display_title = title or ""
            citation = f"[{display_title}]({note_url})" if note_url else display_title

            results.append({
                "id": note_id,
                "title": display_title,
                "folder": folder or "",
                "snippet": (snippet or "")[:200],
                "modification_date": mod_date_str,
                "attachment_count": att_count,
                "note_url": note_url,
                "citation": citation,
            })

        return results
    finally:
        conn.close()


def _create_fts_index(db_path: str) -> None:
    """Create and populate an FTS5 virtual table on the temp DB copy.

    The db_path should be a temp copy (not the original NoteStore), so we
    open it in read-write mode (no ?mode=ro).
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                title, snippet, filename, summary, ocr_summary, url,
                content='', content_rowid='rowid',
                tokenize='porter unicode61'
            )
        """)
        conn.execute("""
            INSERT INTO notes_fts(rowid, title, snippet, filename, summary, ocr_summary, url)
            SELECT note.Z_PK,
                   COALESCE(note.ZTITLE1, ''),
                   COALESCE(note.ZSNIPPET, ''),
                   COALESCE(GROUP_CONCAT(media.ZFILENAME, ' '), ''),
                   COALESCE(note.ZSUMMARY, ''),
                   COALESCE(note.ZOCRSUMMARY, ''),
                   COALESCE((SELECT GROUP_CONCAT(u.ZURLSTRING, ' ')
                             FROM (SELECT DISTINCT mu.ZURLSTRING
                                   FROM ZICCLOUDSYNCINGOBJECT mu
                                   WHERE mu.ZNOTE = note.Z_PK AND mu.ZURLSTRING IS NOT NULL) u), '')
            FROM ZICCLOUDSYNCINGOBJECT note
            LEFT JOIN ZICCLOUDSYNCINGOBJECT att ON att.ZNOTE = note.Z_PK AND att.ZTYPEUTI IS NOT NULL
            LEFT JOIN ZICCLOUDSYNCINGOBJECT media ON media.Z_PK = att.ZMEDIA
            WHERE note.ZTITLE1 IS NOT NULL
            GROUP BY note.Z_PK
        """)
        conn.commit()
    finally:
        conn.close()


def _escape_fts_query(query: str) -> str:
    """Escape a user query for FTS5 MATCH.

    Quotes each word for safety, but preserves trailing * for prefix matching.
    """
    words = query.split()
    if not words:
        return '""'
    escaped = []
    for word in words:
        if word.endswith('*'):
            # Prefix match: quote the stem, append * outside
            stem = word[:-1]
            escaped.append(f'"{stem}"*' if stem else '*')
        else:
            escaped.append(f'"{word}"')
    return " ".join(escaped)


def search_notes_fts(
    db_path: str,
    account_col: str,
    query: str,
    folder_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Full-text search using FTS5 with Porter stemming and ranking.

    Falls back to raising an exception if FTS5 is unavailable, so the
    caller can catch and use LIKE-based search_notes() instead.
    """
    _validate_account_col(account_col)
    _create_fts_index(db_path)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        fts_query = _escape_fts_query(query)

        # Get ranked FTS5 results
        fts_rows = conn.execute(
            "SELECT rowid, rank FROM notes_fts WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()

        if not fts_rows:
            return []

        rowids = [r[0] for r in fts_rows]
        # Preserve FTS5 rank ordering
        rank_order = {r[0]: i for i, r in enumerate(fts_rows)}

        placeholders = ",".join("?" * len(rowids))

        # Build folder scoping CTE and clause if needed
        cte_sql = ""
        cte_params: tuple = ()
        folder_clause = ""
        if folder_name is not None:
            cte_sql, cte_params = _folder_subtree_cte(folder_name)
            folder_clause = " AND note.ZFOLDER IN (SELECT pk FROM subtree)"

        sql = cte_sql + f"""
            SELECT
                note.Z_PK,
                note.ZTITLE1,
                note.ZSNIPPET,
                note.ZMODIFICATIONDATE1,
                note.ZIDENTIFIER,
                (SELECT COUNT(*) FROM ZICCLOUDSYNCINGOBJECT
                 WHERE ZNOTE = note.Z_PK AND ZTYPEUTI IS NOT NULL) AS attachment_count
            FROM ZICCLOUDSYNCINGOBJECT note
            WHERE note.Z_PK IN ({placeholders})
              AND note.ZTITLE1 IS NOT NULL
            {folder_clause}
        """
        params = cte_params + tuple(rowids)
        rows = conn.execute(sql, params).fetchall()

        store_uuid = get_store_uuid(db_path)
        uuid_part = store_uuid if store_uuid else "unknown"

        results = []
        for r in rows:
            pk, title, snippet, mod_date, identifier, att_count = r

            mod_date_str = None
            if mod_date is not None:
                cd_epoch = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
                mod_date_str = (cd_epoch + datetime.timedelta(seconds=mod_date)).isoformat()

            note_id = f"x-coredata://{uuid_part}/ICNote/p{pk}"
            note_url = f"https://james-andrews-coulter.github.io/notes-link/?id={identifier}" if identifier else None

            display_title = title or ""
            citation = f"[{display_title}]({note_url})" if note_url else display_title

            results.append({
                "id": note_id,
                "title": display_title,
                "snippet": (snippet or "")[:200],
                "modification_date": mod_date_str,
                "attachment_count": att_count,
                "match_surface": "fts5",
                "note_url": note_url,
                "citation": citation,
                "_rank_order": rank_order.get(pk, 999),
            })

        # Sort by FTS5 rank order
        results.sort(key=lambda x: x["_rank_order"])
        for r in results:
            del r["_rank_order"]

        return results
    finally:
        conn.close()


def get_note_identifier(db_path: str, note_pk: int) -> str | None:
    """Get the ZIDENTIFIER for a note by its Z_PK."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT ZIDENTIFIER FROM ZICCLOUDSYNCINGOBJECT WHERE Z_PK = ?",
            (note_pk,),
        ).fetchone()
        return row[0] if row else None
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
