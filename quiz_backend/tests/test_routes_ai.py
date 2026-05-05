import asyncio

import pytest
from fastapi import HTTPException

from app.routes import ai as ai_routes
from tests.conftest import StubSupabaseDB, FakeUser


class DummyUploadFile:
    def __init__(self, filename, content_type, content):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self):
        return self._content


def test_generate_questions_disabled_feature_flag(monkeypatch):
    file = DummyUploadFile("notes.pdf", "application/pdf", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", False)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(ai_routes, "_get_ai_service_components", lambda: (None, None, None, {}, 0))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ai_routes.generate_questions(
                file=file,
                topic_id=1,
                question_types="MCQ",
                difficulty=3,
                count=5,
                user=FakeUser("u1"),
            )
        )

    assert exc.value.status_code == 503


def test_generate_questions_rejects_invalid_question_type(monkeypatch):
    file = DummyUploadFile("notes.pdf", "application/pdf", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(
        ai_routes,
        "_get_ai_service_components",
        lambda: (None, None, None, {".pdf": "application/pdf"}, 20 * 1024 * 1024),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ai_routes.generate_questions(
                file=file,
                topic_id=1,
                question_types="ESSAY",
                difficulty=3,
                count=5,
                user=FakeUser("u1"),
            )
        )

    assert exc.value.status_code == 422


def test_generate_questions_rejects_mime_extension_mismatch(monkeypatch):
    file = DummyUploadFile("notes.pdf", "text/plain", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(
        ai_routes,
        "_get_ai_service_components",
        lambda: (None, None, None, {".pdf": "application/pdf"}, 20 * 1024 * 1024),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ai_routes.generate_questions(
                file=file,
                topic_id=1,
                question_types="MCQ",
                difficulty=3,
                count=5,
                user=FakeUser("u1"),
            )
        )

    assert exc.value.status_code == 415


def test_generate_questions_topic_not_found(monkeypatch):
    file = DummyUploadFile("notes.pdf", "application/pdf", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(
        ai_routes,
        "_get_ai_service_components",
        lambda: (None, None, None, {".pdf": "application/pdf"}, 20 * 1024 * 1024),
    )
    monkeypatch.setattr(ai_routes, "supabase_db", StubSupabaseDB({("topics", "select"): [{"data": None}]}))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ai_routes.generate_questions(
                file=file,
                topic_id=999,
                question_types="MCQ",
                difficulty=3,
                count=5,
                user=FakeUser("u1"),
            )
        )

    assert exc.value.status_code == 404


def test_generate_questions_success(monkeypatch):
    file = DummyUploadFile("notes.pdf", "application/pdf", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")

    db = StubSupabaseDB({
        ("topics", "select"): [{"data": {"id": 1, "name": "Biology"}}],
    })
    monkeypatch.setattr(ai_routes, "supabase_db", db)

    async def fake_generate_all_questions(**kwargs):
        assert kwargs["filename"] == "notes.pdf"
        assert kwargs["mime_type"] == "application/pdf"
        assert kwargs["topic_name"] == "Biology"
        assert kwargs["requests"] == [{"type": "MCQ", "difficulty": 3, "count": 1}]
        return [[{
            "text": "What is the powerhouse of the cell?",
            "type": "MCQ",
            "options": {"A": "Nucleus", "B": "Mitochondria", "C": "Ribosome", "D": "Membrane"},
            "answer": "B",
            "keywords": None,
            "tolerance": None,
            "difficulty": 3,
            "explanation": "Mitochondria produce ATP.",
        }]]

    monkeypatch.setattr(
        ai_routes,
        "_get_ai_service_components",
        lambda: (None, fake_generate_all_questions, None, {".pdf": "application/pdf"}, 20 * 1024 * 1024),
    )

    out = asyncio.run(
        ai_routes.generate_questions(
            file=file,
            topic_id=1,
            question_types="MCQ",
            difficulty=3,
            count=1,
            user=FakeUser("u1"),
        )
    )

    assert out["count"] == 1
    assert out["generated"][0]["text"] == "What is the powerhouse of the cell?"
    assert out["generated"][0]["difficulty"] == 3
    assert out["validation_warnings"] == []
    assert out["topic_id"] == 1


def test_generate_questions_rejects_invalid_ai_shape(monkeypatch):
    file = DummyUploadFile("notes.pdf", "application/pdf", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")

    db = StubSupabaseDB({
        ("topics", "select"): [{"data": {"id": 1, "name": "Biology"}}],
    })
    monkeypatch.setattr(ai_routes, "supabase_db", db)

    async def fake_generate_all_questions(**kwargs):
        return [[{"text": "Broken payload", "type": "MCQ"}]]

    monkeypatch.setattr(
        ai_routes,
        "_get_ai_service_components",
        lambda: (None, fake_generate_all_questions, None, {".pdf": "application/pdf"}, 20 * 1024 * 1024),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ai_routes.generate_questions(
                file=file,
                topic_id=1,
                question_types="MCQ",
                difficulty=3,
                count=1,
                user=FakeUser("u1"),
            )
        )

    assert exc.value.status_code == 422
    assert "options" in exc.value.detail.lower()


def test_generate_questions_returns_warnings_for_soft_fixes(monkeypatch):
    file = DummyUploadFile("notes.pdf", "application/pdf", b"pdf-content")
    monkeypatch.setattr(ai_routes.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_routes.settings, "GEMINI_API_KEY", "key")

    db = StubSupabaseDB({
        ("topics", "select"): [{"data": {"id": 1, "name": "Biology"}}],
    })
    monkeypatch.setattr(ai_routes, "supabase_db", db)

    async def fake_generate_all_questions(**kwargs):
        return [[
            {
                "text": "What is ATP used for?",
                "type": "mcq",
                "options": {
                    "a": "Cell signaling",
                    "b": "Energy transfer",
                    "c": "DNA storage",
                    "d": "Protein folding",
                    "e": "extra option",
                },
                "answer": "b",
                "explanation": 123,
            },
            {
                "text": "Extra question that should be truncated",
                "type": "MCQ",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "A",
            },
        ]]

    monkeypatch.setattr(
        ai_routes,
        "_get_ai_service_components",
        lambda: (None, fake_generate_all_questions, None, {".pdf": "application/pdf"}, 20 * 1024 * 1024),
    )

    out = asyncio.run(
        ai_routes.generate_questions(
            file=file,
            topic_id=1,
                question_types="MCQ",
            difficulty=3,
            count=1,
            user=FakeUser("u1"),
        )
    )

    assert out["count"] == 1
    assert out["generated"][0]["answer"] == "B"
    assert len(out["validation_warnings"]) >= 1
