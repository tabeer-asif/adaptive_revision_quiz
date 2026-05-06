"""Integration tests for /auth/* endpoints.

Auth routes use supabase_auth and supabase_db directly (not via dependency injection),
so each test monkeypatches those objects at the module level.
"""
import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from app.main import app


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_auth(sign_up_user=None, sign_in_session=None, sign_in_user=None, get_user=None):
    """Build a minimal supabase_auth stub."""
    class _Auth:
        def sign_up(self, _):
            return SimpleNamespace(user=sign_up_user)

        def sign_in_with_password(self, _):
            if sign_in_session is None:
                raise Exception("Invalid credentials")
            return SimpleNamespace(session=sign_in_session, user=sign_in_user)

        def get_user(self, token):
            if get_user is None:
                raise Exception("invalid token")
            return SimpleNamespace(user=get_user)

    return SimpleNamespace(auth=_Auth())


# ── Register ───────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, monkeypatch):
        fake_user = SimpleNamespace(id="new-user-id")
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth(sign_up_user=fake_user))

        from tests.conftest import StubSupabaseDB
        db = StubSupabaseDB({("users", "insert"): [{"data": [{"id": "new-user-id"}]}]})
        monkeypatch.setattr("app.routes.auth.supabase_db", db)

        with TestClient(app) as c:
            r = c.post("/auth/register", json={
                "email": "alice@example.com",
                "password": "secret123",
                "first_name": "Alice",
                "surname": "Smith",
            })

        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == "new-user-id"
        assert "registered" in body["message"].lower()

    def test_register_auth_failure_returns_400(self, monkeypatch):
        # Supabase Auth returns None user → 400
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth(sign_up_user=None))

        with TestClient(app) as c:
            r = c.post("/auth/register", json={"email": "x@x.com", "password": "pw"})

        assert r.status_code == 400

    def test_register_db_failure_returns_500(self, monkeypatch):
        fake_user = SimpleNamespace(id="uid")
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth(sign_up_user=fake_user))

        from tests.conftest import StubSupabaseDB
        # DB insert raises to simulate failure
        class FailDB:
            def table(self, _):
                class Q:
                    def insert(self, _): return self
                    def execute(self): raise RuntimeError("DB down")
                return Q()
        monkeypatch.setattr("app.routes.auth.supabase_db", FailDB())

        with TestClient(app) as c:
            r = c.post("/auth/register", json={"email": "x@x.com", "password": "pw"})

        assert r.status_code == 500


# ── Login ──────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success(self, monkeypatch):
        session = SimpleNamespace(access_token="tok-abc")
        user = SimpleNamespace(id="uid-1")
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth(
            sign_in_session=session, sign_in_user=user
        ))

        with TestClient(app) as c:
            r = c.post("/auth/login", json={"email": "a@b.com", "password": "pw"})

        assert r.status_code == 200
        body = r.json()
        assert body["access_token"] == "tok-abc"
        assert body["user_id"] == "uid-1"

    def test_login_invalid_credentials_returns_401(self, monkeypatch):
        # sign_in_with_password raises → 401
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth())

        with TestClient(app) as c:
            r = c.post("/auth/login", json={"email": "a@b.com", "password": "wrong"})

        assert r.status_code == 401
        assert "invalid" in r.json()["detail"].lower()


# ── Verify token ───────────────────────────────────────────────────────────────

class TestVerifyToken:
    def test_verify_token_valid(self, monkeypatch):
        fake_user = SimpleNamespace(id="uid-1")
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth(get_user=fake_user))

        with TestClient(app) as c:
            r = c.get("/auth/verify-token", headers={"Authorization": "Bearer good-token"})

        assert r.status_code == 200
        assert r.json()["user_id"] == "uid-1"

    def test_verify_token_invalid_returns_401(self, monkeypatch):
        monkeypatch.setattr("app.routes.auth.supabase_auth", _make_auth(get_user=None))

        with TestClient(app) as c:
            r = c.get("/auth/verify-token", headers={"Authorization": "Bearer bad-token"})

        assert r.status_code == 401

    def test_verify_token_bad_format_returns_401(self):
        with TestClient(app) as c:
            r = c.get("/auth/verify-token", headers={"Authorization": "NotBearer xyz"})

        assert r.status_code == 401
