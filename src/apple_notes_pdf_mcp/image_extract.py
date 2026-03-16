"""Image encoding for Apple Notes attachments."""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile


def encode_image(
    file_path: str,
    max_size_bytes: int = 1_048_576,
) -> dict:
    """Encode an image file as base64 for MCP ImageContent.

    Handles HEIC (converts to JPEG via sips), PNG, and JPEG.
    Resizes if over max_size_bytes.

    Returns dict with: data (base64 str), mime_type, size_bytes, error.
    """
    if not os.path.exists(file_path):
        return {"data": None, "mime_type": None, "size_bytes": 0, "error": "not_downloaded"}

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext in ('.heic', '.heif'):
            # Convert HEIC to JPEG via sips
            data, mime = _convert_heic(file_path, max_size_bytes)
        elif ext == '.png':
            data = _read_and_resize(file_path, max_size_bytes, "png")
            mime = "image/png"
        elif ext in ('.jpg', '.jpeg'):
            data = _read_and_resize(file_path, max_size_bytes, "jpeg")
            mime = "image/jpeg"
        else:
            return {"data": None, "mime_type": None, "size_bytes": 0, "error": f"unsupported_format_{ext}"}

        encoded = base64.standard_b64encode(data).decode("ascii")
        return {
            "data": encoded,
            "mime_type": mime,
            "size_bytes": len(data),
            "error": None,
        }
    except Exception as e:
        return {"data": None, "mime_type": None, "size_bytes": 0, "error": str(e)}


def _convert_heic(file_path: str, max_size_bytes: int) -> tuple[bytes, str]:
    """Convert HEIC to JPEG using macOS sips."""
    with tempfile.NamedTemporaryFile(suffix=".jpeg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", file_path, "--out", tmp_path],
            capture_output=True, timeout=30, check=True,
        )
        data = _read_and_resize(tmp_path, max_size_bytes, "jpeg")
        return data, "image/jpeg"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _read_and_resize(file_path: str, max_size_bytes: int, fmt: str) -> bytes:
    """Read image bytes, resizing if over max_size_bytes."""
    data = open(file_path, "rb").read()
    if len(data) <= max_size_bytes:
        return data

    # Resize using sips to reduce size
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        # Calculate scale factor based on size ratio (area scales quadratically)
        scale = (max_size_bytes / len(data)) ** 0.5
        # Get current dimensions
        result = subprocess.run(
            ["sips", "-g", "pixelHeight", file_path],
            capture_output=True, text=True, timeout=10,
        )
        height = 1000  # fallback
        for line in result.stdout.splitlines():
            if "pixelHeight" in line:
                height = int(line.split()[-1])
                break
        new_height = max(100, int(height * scale))

        subprocess.run(
            ["sips", "--resampleHeight", str(new_height), file_path, "--out", tmp_path],
            capture_output=True, timeout=30, check=True,
        )
        return open(tmp_path, "rb").read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
