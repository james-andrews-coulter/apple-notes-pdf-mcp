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
            # Verify "Work" appears in the JXA script
            script = call_args[4]  # -l JavaScript -e <script>
            assert "Work" in script

    def test_empty_output(self):
        with _mock_osascript(""):
            notes = list_notes()
        assert notes == []


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

    def test_search_empty_results(self):
        with _mock_osascript("[]"):
            results = search_notes("nonexistent")
        assert results == []


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
        assert note["attachments"][0]["name"] == "doc.pdf"
