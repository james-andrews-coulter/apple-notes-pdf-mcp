import json
from unittest.mock import patch, MagicMock
from apple_notes_pdf_mcp.applescript import list_notes, get_note


def _mock_osascript(output: str):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = output
    mock.stderr = ""
    return patch("subprocess.run", return_value=mock)


def test_list_notes_parses_json():
    output = json.dumps([{
        "id": "x-coredata://123/ICNote/p456",
        "title": "Test Note",
        "folder": "Notes",
        "snippet": "Some text",
        "modification_date": "2026-03-10T14:22:00Z",
        "attachment_count": 1,
    }])
    with _mock_osascript(output):
        notes = list_notes()
    assert len(notes) == 1
    assert notes[0]["title"] == "Test Note"


def test_get_note_returns_body_and_attachments():
    output = json.dumps({
        "id": "x-coredata://123/ICNote/p456",
        "title": "Test Note",
        "body": "Full body text",
        "folder": "Notes",
        "modification_date": "2026-03-10T14:22:00Z",
        "attachments": [{"name": "doc.pdf", "type": "com.adobe.pdf"}],
    })
    with _mock_osascript(output):
        note = get_note("x-coredata://123/ICNote/p456")
    assert note["body"] == "Full body text"
    assert note["attachments"][0]["name"] == "doc.pdf"
