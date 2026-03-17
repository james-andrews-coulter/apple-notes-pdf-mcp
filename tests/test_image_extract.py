from unittest.mock import patch, MagicMock
from apple_notes_pdf_mcp.image_extract import encode_image


def test_encode_jpeg(tmp_path):
    jpeg = tmp_path / "test.jpeg"
    jpeg.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100 + b'\xff\xd9')
    result = encode_image(str(jpeg))
    assert result["data"] is not None
    assert result["mime_type"] == "image/jpeg"
    assert result["error"] is None


def test_encode_missing_file():
    result = encode_image("/nonexistent/image.jpg")
    assert result["error"] == "not_downloaded"


def test_encode_heic_converts_via_sips(tmp_path):
    heic = tmp_path / "test.heic"
    heic.write_bytes(b'\x00' * 100)
    jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 50 + b'\xff\xd9'

    def fake_sips(*args, **kwargs):
        cmd = args[0]
        if "--out" in cmd:
            with open(cmd[cmd.index("--out") + 1], "wb") as f:
                f.write(jpeg_bytes)
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_sips):
        result = encode_image(str(heic))
    assert result["mime_type"] == "image/jpeg"
    assert result["error"] is None
