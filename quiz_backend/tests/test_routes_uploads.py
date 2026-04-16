import asyncio
import pytest
from fastapi import HTTPException

from app.routes import uploads
from tests.conftest import FakeUser


"""Tests for image upload route validation and Supabase storage integration."""


class DummyUploadFile:
    def __init__(self, filename, content_type, content):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self):
        return self._content


class DummyBucket:
    def __init__(self, fail_upload=False, public_url="https://cdn.example/image.png"):
        self.fail_upload = fail_upload
        self.public_url = public_url
        self.upload_calls = []

    def upload(self, path, file, file_options=None):
        if self.fail_upload:
            raise RuntimeError("boom")
        self.upload_calls.append({
            "path": path,
            "file": file,
            "file_options": file_options or {},
        })

    def get_public_url(self, path):
        return self.public_url


class DummyStorage:
    def __init__(self, bucket):
        self.bucket = bucket
        self.bucket_name = None

    def from_(self, bucket_name):
        self.bucket_name = bucket_name
        return self.bucket


class DummySupabase:
    def __init__(self, bucket):
        self.storage = DummyStorage(bucket)


def test_upload_question_image_rejects_unsupported_type():
    file = DummyUploadFile("q.txt", "text/plain", b"hello")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads.upload_question_image(file=file, user=FakeUser("u1")))

    assert exc.value.status_code == 415


def test_upload_question_image_rejects_large_file():
    too_large = b"\x89PNG\r\n\x1a\n" + (b"a" * uploads.MAX_SIZE_BYTES)
    file = DummyUploadFile("q.png", "image/png", too_large)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads.upload_question_image(file=file, user=FakeUser("u1")))

    assert exc.value.status_code == 413


def test_upload_question_image_success(monkeypatch):
    bucket = DummyBucket(public_url="https://cdn.example/q.png")
    monkeypatch.setattr(uploads, "supabase_db", DummySupabase(bucket))

    file = DummyUploadFile("q.png", "image/png", b"\x89PNG\r\n\x1a\nrest")
    out = asyncio.run(uploads.upload_question_image(file=file, user=FakeUser("user-123")))

    assert out["image_url"] == "https://cdn.example/q.png"
    assert out["filename"].startswith("user-123/")
    assert out["filename"].endswith(".png")
    assert bucket.upload_calls[0]["file_options"]["content-type"] == "image/png"


def test_upload_question_image_handles_storage_fail(monkeypatch):
    bucket = DummyBucket(fail_upload=True)
    monkeypatch.setattr(uploads, "supabase_db", DummySupabase(bucket))

    file = DummyUploadFile("q.png", "image/png", b"\x89PNG\r\n\x1a\nrest")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads.upload_question_image(file=file, user=FakeUser("u1")))

    assert exc.value.status_code == 500
    assert "Upload failed" in exc.value.detail


def test_upload_question_image_rejects_magic_byte_mismatch():
    # Declared PNG but JPEG signature should be rejected.
    file = DummyUploadFile("q.png", "image/png", b"\xff\xd8\xffsomething")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads.upload_question_image(file=file, user=FakeUser("u1")))

    assert exc.value.status_code == 415
