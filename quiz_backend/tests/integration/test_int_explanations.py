"""Integration tests for /explanations/explain and /explanations/chat endpoints.

Both endpoints import generate_explanation / generate_chat_reply inside the
route handler at call time, so we monkeypatch at the service module level.
"""
import pytest
from tests.integration.conftest import USER_ID

# ── Fixtures ───────────────────────────────────────────────────────────────────

_QUESTION = {
    "id": 1,
    "topic_id": 10,
    "type": "MCQ",
    "text": "What is 2+2?",
    "options": {"A": "3", "B": "4"},
    "answer": "B",
    "difficulty": 2,
    "explanation": "Basic arithmetic.",
    "irt_a": 1.0, "irt_b": 0.0, "irt_c": 0.25,
    "n_responses": 5, "n_correct": 4,
    "created_by": USER_ID,
}

_THETA_ROW = {
    "user_id": USER_ID,
    "topic_id": 10,
    "theta": 0.5,
    "theta_variance": 1.0,
    "n_responses": 10,
    "is_calibrated": False,
}

_REVIEW_ROWS = [
    {"question_id": 1, "correct": True, "rating": 3},
    {"question_id": 1, "correct": False, "rating": 2},
]


async def _fake_generate_explanation(*args, **kwargs):
    return {"explanation": "Mitochondria are called the powerhouse because they produce ATP."}


async def _fake_generate_chat_reply(*args, **kwargs):
    return "Great question! Here is more detail about ATP synthesis."


def _patch_ai_services(monkeypatch, ai_enabled=True):
    import app.config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "AI_ENABLED", ai_enabled)
    monkeypatch.setattr(cfg_mod.settings, "GEMINI_API_KEY", "fake-key" if ai_enabled else "")

    import app.services.ai as svc
    monkeypatch.setattr(svc, "generate_explanation", _fake_generate_explanation)
    monkeypatch.setattr(svc, "generate_chat_reply", _fake_generate_chat_reply)


# ── /explanations/explain ──────────────────────────────────────────────────────

class TestExplain:
    def test_returns_explanation(self, client, auth_headers, make_db, monkeypatch):
        make_db({
            ("questions", "select"): [{"data": _QUESTION}],
            ("user_topic_theta", "select"): [{"data": [_THETA_ROW]}],
            ("review_logs", "select"): [{"data": _REVIEW_ROWS}],
        })
        _patch_ai_services(monkeypatch)

        r = client.post(
            "/explanations/explain",
            json={
                "question_id": 1,
                "topic_id": 10,
                "selected_option": "B",
            },
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert "explanation" in body
        assert len(body["explanation"]) > 0

    def test_question_not_found_returns_404(self, client, auth_headers, make_db, monkeypatch):
        make_db({
            ("questions", "select"): [{"data": None}],
        })
        _patch_ai_services(monkeypatch)

        r = client.post(
            "/explanations/explain",
            json={
                "question_id": 999,
                "topic_id": 10,
                "selected_option": "A",
            },
            headers=auth_headers,
        )

        assert r.status_code == 404

    def test_ai_disabled_returns_503(self, client, auth_headers, monkeypatch):
        _patch_ai_services(monkeypatch, ai_enabled=False)

        r = client.post(
            "/explanations/explain",
            json={
                "question_id": 1,
                "topic_id": 10,
                "selected_option": "A",
            },
            headers=auth_headers,
        )

        assert r.status_code == 503

    def test_requires_auth(self, client, no_auth):
        r = client.post(
            "/explanations/explain",
            json={"question_id": 1, "topic_id": 10, "selected_option": "A"},
        )
        assert r.status_code in (401, 403)


# ── /explanations/chat ─────────────────────────────────────────────────────────

class TestChat:
    def test_returns_reply(self, client, auth_headers, make_db, monkeypatch):
        make_db({
            ("questions", "select"): [{"data": _QUESTION}],
            ("user_topic_theta", "select"): [{"data": [_THETA_ROW]}],
        })
        _patch_ai_services(monkeypatch)

        r = client.post(
            "/explanations/chat",
            json={
                "question_id": 1,
                "topic_id": 10,
                "user_answer": {"selected_option": "B"},
                "history": [],
                "message": "Can you explain this further?",
            },
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert "reply" in body
        assert len(body["reply"]) > 0

    def test_ai_disabled_returns_503(self, client, auth_headers, monkeypatch):
        _patch_ai_services(monkeypatch, ai_enabled=False)

        r = client.post(
            "/explanations/chat",
            json={
                "question_id": 1,
                "topic_id": 10,
                "user_answer": {"selected_option": "B"},
                "history": [],
                "message": "Help me understand.",
            },
            headers=auth_headers,
        )

        assert r.status_code == 503

    def test_topic_mismatch_returns_400(self, client, auth_headers, make_db, monkeypatch):
        make_db({
            # question belongs to topic_id=10 but request sends topic_id=99
            ("questions", "select"): [{"data": _QUESTION}],
        })
        _patch_ai_services(monkeypatch)

        r = client.post(
            "/explanations/chat",
            json={
                "question_id": 1,
                "topic_id": 99,   # mismatch
                "user_answer": {"selected_option": "A"},
                "history": [],
                "message": "?",
            },
            headers=auth_headers,
        )

        # 400 or 404 depending on implementation; either indicates rejection
        assert r.status_code in (400, 404)

    def test_requires_auth(self, client, no_auth):
        r = client.post(
            "/explanations/chat",
            json={
                "question_id": 1,
                "topic_id": 10,
                "user_answer": {"selected_option": "B"},
                "history": [],
                "message": "?",
            },
        )
        assert r.status_code in (401, 403)
