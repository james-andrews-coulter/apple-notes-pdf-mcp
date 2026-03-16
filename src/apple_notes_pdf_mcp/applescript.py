"""AppleScript wrappers for Apple Notes access via osascript."""

from __future__ import annotations

import json
import subprocess


def _run_jxa(script: str, timeout: int = 60) -> str:
    """Run a JXA (JavaScript for Automation) script and return stdout."""
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"JXA error: {result.stderr}")
    return result.stdout.strip()


def list_notes(folder: str | None = None) -> list[dict]:
    """List all notes with basic metadata.

    Uses JXA (JavaScript for Automation) instead of AppleScript for
    reliable JSON output without escaping issues.
    """
    folder_filter = ""
    if folder:
        folder_filter = f'.folders.byName("{folder}")'

    script = f"""
    const app = Application("Notes");
    const notes = app{folder_filter}.notes();
    const result = notes.map(n => {{
        const body = n.plaintext();
        return {{
            id: n.id(),
            title: n.name(),
            folder: n.container().name(),
            snippet: body.substring(0, 200),
            modification_date: n.modificationDate().toISOString(),
            attachment_count: n.attachments().length
        }};
    }});
    JSON.stringify(result);
    """
    output = _run_jxa(script)
    if not output:
        return []
    return json.loads(output)


def search_notes(query: str) -> list[dict]:
    """Search notes by title and body text. Case-insensitive."""
    # Escape the query for use in JavaScript string
    safe_query = query.replace("\\", "\\\\").replace('"', '\\"')

    script = f"""
    const app = Application("Notes");
    const byBody = app.notes.whose({{plaintext: {{_contains: "{safe_query}"}}}})();
    const byTitle = app.notes.whose({{name: {{_contains: "{safe_query}"}}}})();
    const seen = new Set();
    const all = [...byBody, ...byTitle];
    const result = [];
    for (const n of all) {{
        const nid = n.id();
        if (seen.has(nid)) continue;
        seen.add(nid);
        const body = n.plaintext();
        result.push({{
            id: nid,
            title: n.name(),
            folder: n.container().name(),
            snippet: body.substring(0, 200),
            modification_date: n.modificationDate().toISOString(),
            attachment_count: n.attachments().length
        }});
    }}
    JSON.stringify(result);
    """
    output = _run_jxa(script)
    if not output:
        return []
    return json.loads(output)


def get_note(note_id: str) -> dict:
    """Get a single note's full body text and attachment metadata."""
    safe_id = note_id.replace("\\", "\\\\").replace('"', '\\"')

    script = f"""
    const app = Application("Notes");
    const n = app.notes.byId("{safe_id}");
    const atts = n.attachments().map(a => ({{
        name: a.name(),
        type: a.contentIdentifier()
    }}));
    const result = {{
        id: n.id(),
        title: n.name(),
        body: n.plaintext(),
        folder: n.container().name(),
        modification_date: n.modificationDate().toISOString(),
        attachments: atts
    }};
    JSON.stringify(result);
    """
    output = _run_jxa(script)
    return json.loads(output)
