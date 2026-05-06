"""Integration tests for /ai/* endpoints.

Both endpoints expect multipart form + file upload.
We monkeypatch _get_ai_service_components to avoid real Gemini calls.
"""
import io
import pytest

# ── Fakes ──────────────────────────────────────────────────────────────────────

_QUESTION = {
    "type": "MCQ",
    "text": "What is the powerhouse of the cell?",
    "options": {"A": "Nucleus", "B": "Mitochondria", "C": "Ribosome", "D": "Membrane"},
    "answer": "B",
    "explanation": "Mitochondria produce ATP.",
    "difficulty": 2,
}

# generate_all_questions returns list-of-lists (one per request)
async def _fake_generate_all_questions(**kwargs):
    return [[_QUESTION]]


async def _fake_score_feasibility(file_bytes, filename, mime_type):
    return {"MCQ": 0.9, "SHORT": 0.7, "NUMERIC": 0.2, "MULTI_MCQ": 0.5, "OPEN": 0.6}


def _patch_ai_components(monkeypatch, ai_enabled=True):
    supported_types = {".pdf": "application/pdf", ".txt": "text/plain"}

    def _fake_get_components():
        return (
            None,                          # generate_questions_from_file (unused)
            _fake_generate_all_questions,
            _fake_score_feasibility,
            supported_types,
            20 * 1024 * 1024,
        )

    import app.routes.ai as ai_mod
    monkeypatch.setattr(ai_mod, "_get_ai_service_components", _fake_get_components)

    import app.config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "AI_ENABLED", ai_enabled)
    monkeypatch.setattr(cfg_mod.settings, "GEMINI_API_KEY", "fake-key" if ai_enabled else "")


# ── /ai/generate-questions ─────────────────────────────────────────────────────

class TestGenerateQuestions:
    def test_generates_mcq_questions(self, client, auth_headers, make_db, monkeypatch):
        make_db({
            ("topics", "select"): [{"data": {"id": 1, "name": "Biology"}}],
        })
        _patch_ai_components(monkeypatch)

        r = client.post(
            "/ai/generate-questions",
            data={
                "topic_id": "1",
                "question_type": "MCQ",
                "difficulty": "2",
                "count": "1",
            },
            files={"file": ("notes.txt", io.BytesIO(b"Mitochondria produce ATP in cells."), "text/plain")},
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert "generated" in body
        assert len(body["generated"]) >= 1

    def test_ai_disabled_returns_503(self, client, auth_headers, monkeypatch):
        _patch_ai_components(monkeypatch, ai_enabled=False)

        r = client.post(
            "/ai/generate-questions",
            data={
                "topic_id": "1",
                "question_type": "MCQ",
                "difficulty": "2",
                "count": "1",
            },
            files={"file": ("notes.txt", io.BytesIO(b"Some content."), "text/plain")},
            headers=auth_headers,
        )

        assert r.status_code == 503

    def test_unsupported_file_type_returns_415(self, client, auth_headers, make_db, monkeypatch):
        make_db({
            ("topics", "select"): [{"data": {"id": 1, "name": "Biology"}}],
        })
        _patch_ai_components(monkeypatch)

        r = client.post(
            "/ai/generate-questions",
            data={
                "topic_id": "1",
                "question_type": "MCQ",
                "difficulty": "2",
                "count": "1",
            },
            files={"file": ("image.png", io.BytesIO(b"\x89PNG data"), "image/png")},
            headers=auth_headers,
        )

        assert r.status_code == 415

    def test_requires_auth(self, client, no_auth):
        r = client.post(
            "/ai/generate-questions",
            data={"topic_id": "1", "question_type": "MCQ", "difficulty": "2", "count": "1"},
            files={"file": ("notes.txt", io.BytesIO(b"content"), "text/plain")},
        )
        assert r.status_code in (401, 403)


# ── /ai/feasibility ────────────────────────────────────────────────────────────

class TestFeasibility:
    def test_pdf_feasibility_returns_scores(self, client, auth_headers, monkeypatch):
        _patch_ai_components(monkeypatch)

        r = client.post(
            "/ai/feasibility",
            files={"file": ("notes.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert "scores" in body
        assert "MCQ" in body["scores"]

    def test_unsupported_file_type_returns_400(self, client, auth_headers, monkeypatch):
        _patch_ai_components(monkeypatch)

        r = client.post(
            "/ai/feasibility",
            files={"file": ("img.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")},
            headers=auth_headers,
        )

        assert r.status_code == 400

    def test_requires_auth(self, client, no_auth):
        r = client.post(
            "/ai/feasibility",
            files={"file": ("notes.pdf", io.BytesIO(b"%PDF content"), "application/pdf")},
        )
        assert r.status_code in (401, 403)

