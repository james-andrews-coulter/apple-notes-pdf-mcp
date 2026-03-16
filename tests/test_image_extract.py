import pytest
from unittest.mock import patch, MagicMock
from apple_notes_pdf_mcp.image_extract import encode_image


def test_encode_jpeg(tmp_path):
    """JPEG passthrough works."""
    # Create a minimal JPEG (SOI + EOI markers)
    jpeg = tmp_path / "test.jpeg"
    jpeg.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100 + b'\xff\xd9')
    result = encode_image(str(jpeg))
    assert result["data"] is not None
    assert result["mime_type"] == "image/jpeg"
    assert result["error"] is None


def test_encode_png(tmp_path):
    """PNG passthrough works."""
    png = tmp_path / "test.png"
    # Minimal valid PNG
    import struct, zlib
    def minimal_png():
        sig = b'\x89PNG\r\n\x1a\n'
        # IHDR
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff)
        # IDAT
        raw = zlib.compress(b'\x00\x00\x00\x00')
        idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', zlib.crc32(b'IDAT' + raw) & 0xffffffff)
        # IEND
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
        return sig + ihdr + idat + iend
    png.write_bytes(minimal_png())
    result = encode_image(str(png))
    assert result["data"] is not None
    assert result["mime_type"] == "image/png"


def test_encode_nonexistent():
    result = encode_image("/nonexistent/image.jpg")
    assert result["data"] is None
    assert result["error"] == "not_downloaded"


def test_encode_heic_calls_sips(tmp_path):
    """HEIC conversion calls sips."""
    heic = tmp_path / "test.heic"
    heic.write_bytes(b'\x00' * 100)

    jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 50 + b'\xff\xd9'

    def fake_sips(*args, **kwargs):
        cmd = args[0]
        if "--out" in cmd:
            out_path = cmd[cmd.index("--out") + 1]
            with open(out_path, "wb") as f:
                f.write(jpeg_bytes)
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_sips):
        result = encode_image(str(heic))
    assert result["mime_type"] == "image/jpeg"
    assert result["error"] is None


def test_encode_unsupported_format(tmp_path):
    bmp = tmp_path / "test.bmp"
    bmp.write_bytes(b'\x00' * 100)
    result = encode_image(str(bmp))
    assert result["error"].startswith("unsupported_format")
