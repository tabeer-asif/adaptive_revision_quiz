"""Integration tests for /uploads/question-image endpoint."""
import io
import pytest

# Valid magic bytes for each format
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff\xe0"
_WEBP_MAGIC = b"RIFF" + b"\x00" * 4 + b"WEBP"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_png(size_bytes=1024):
    """Return bytes that look like a real PNG (magic header + padding)."""
    return _PNG_MAGIC + b"\x00" * (size_bytes - len(_PNG_MAGIC))


def _make_jpeg(size_bytes=1024):
    return _JPEG_MAGIC + b"\x00" * (size_bytes - len(_JPEG_MAGIC))


def _make_webp(size_bytes=1024):
    return _WEBP_MAGIC + b"\x00" * (size_bytes - len(_WEBP_MAGIC))


def _fake_storage(monkeypatch, public_url="https://cdn.example.com/img.png"):
    """Patch supabase_db storage methods for uploads route."""
    import types

    class _StorageBucket:
        def upload(self, *args, **kwargs):
            return {"path": "some/path"}

        def get_public_url(self, path):
            return public_url

    class _StorageClient:
        def from_(self, bucket_name):
            return _StorageBucket()

    class _FakeDB:
        @property
        def storage(self):
            return _StorageClient()

    import app.routes.uploads as uploads_mod
    monkeypatch.setattr(uploads_mod, "supabase_db", _FakeDB())


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestUploadQuestionImage:
    def test_png_upload_returns_url(self, client, auth_headers, monkeypatch):
        _fake_storage(monkeypatch)

        r = client.post(
            "/uploads/question-image",
            files={"file": ("test.png", io.BytesIO(_make_png()), "image/png")},
            headers=auth_headers,
        )

        assert r.status_code == 200
        assert "image_url" in r.json()

    def test_jpeg_upload_returns_url(self, client, auth_headers, monkeypatch):
        _fake_storage(monkeypatch)

        r = client.post(
            "/uploads/question-image",
            files={"file": ("test.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
            headers=auth_headers,
        )

        assert r.status_code == 200
        assert "image_url" in r.json()

    def test_webp_upload_returns_url(self, client, auth_headers, monkeypatch):
        _fake_storage(monkeypatch)

        r = client.post(
            "/uploads/question-image",
            files={"file": ("test.webp", io.BytesIO(_make_webp()), "image/webp")},
            headers=auth_headers,
        )

        assert r.status_code == 200
        assert "image_url" in r.json()

    def test_unsupported_mime_returns_415(self, client, auth_headers):
        r = client.post(
            "/uploads/question-image",
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            headers=auth_headers,
        )

        assert r.status_code == 415

    def test_file_too_large_returns_413(self, client, auth_headers):
        # Slightly over 5 MB
        big_file = _PNG_MAGIC + b"\x00" * (5 * 1024 * 1024 + 1)

        r = client.post(
            "/uploads/question-image",
            files={"file": ("big.png", io.BytesIO(big_file), "image/png")},
            headers=auth_headers,
        )

        assert r.status_code == 413

    def test_wrong_magic_bytes_returns_415(self, client, auth_headers):
        # Declare content-type as PNG but send PDF bytes
        r = client.post(
            "/uploads/question-image",
            files={"file": ("fake.png", io.BytesIO(b"%PDF-1.4 fake data"), "image/png")},
            headers=auth_headers,
        )

        assert r.status_code == 415

    def test_requires_auth(self, client, no_auth):
        r = client.post(
            "/uploads/question-image",
            files={"file": ("t.png", io.BytesIO(_make_png()), "image/png")},
        )
        assert r.status_code in (401, 403)
