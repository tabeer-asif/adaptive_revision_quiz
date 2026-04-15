import pytest
from fastapi import HTTPException

from app.routes import auth as auth_routes
from tests.conftest import FakeSupabaseAuthClient, FakeAuthModule, StubSupabaseDB


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_register_success(monkeypatch):
    auth_mod = FakeAuthModule()
    auth_mod.sign_up_result = Obj(user=Obj(id="user-1"))
    monkeypatch.setattr(auth_routes, "supabase_auth", FakeSupabaseAuthClient(auth_mod))

    db = StubSupabaseDB({("users", "insert"): [{"data": [{"id": "user-1"}]}]})
    monkeypatch.setattr(auth_routes, "supabase_db", db)

    out = auth_routes.register({"email": "a@b.com", "password": "x", "first_name": "A", "surname": "B"})
    assert out["user_id"] == "user-1"


def test_register_fail_sign_up(monkeypatch):
    auth_mod = FakeAuthModule()
    auth_mod.sign_up_result = Obj(user=None)
    monkeypatch.setattr(auth_routes, "supabase_auth", FakeSupabaseAuthClient(auth_mod))
    monkeypatch.setattr(auth_routes, "supabase_db", StubSupabaseDB())

    with pytest.raises(HTTPException) as exc:
        auth_routes.register({"email": "a@b.com", "password": "x"})
    assert exc.value.status_code == 400


def test_register_fail_db(monkeypatch):
    auth_mod = FakeAuthModule()
    auth_mod.sign_up_result = Obj(user=Obj(id="user-1"))
    monkeypatch.setattr(auth_routes, "supabase_auth", FakeSupabaseAuthClient(auth_mod))

    class BoomDB(StubSupabaseDB):
        def table(self, name):
            raise RuntimeError("db fail")

    monkeypatch.setattr(auth_routes, "supabase_db", BoomDB())

    with pytest.raises(HTTPException) as exc:
        auth_routes.register({"email": "a@b.com", "password": "x"})
    assert exc.value.status_code == 500


def test_login_success_and_failure(monkeypatch):
    auth_mod = FakeAuthModule()
    auth_mod.sign_in_result = Obj(session=Obj(access_token="token"), user=Obj(id="uid"))
    monkeypatch.setattr(auth_routes, "supabase_auth", FakeSupabaseAuthClient(auth_mod))

    out = auth_routes.login({"email": "a@b.com", "password": "x"})
    assert out["access_token"] == "token"

    auth_mod.sign_in_error = RuntimeError("bad creds")
    with pytest.raises(HTTPException) as exc:
        auth_routes.login({"email": "a@b.com", "password": "x"})
    assert exc.value.status_code == 401


def test_verify_token_paths(monkeypatch):
    auth_mod = FakeAuthModule()
    auth_mod.get_user_result = Obj(user=Obj(id="uid"))
    monkeypatch.setattr(auth_routes, "supabase_auth", FakeSupabaseAuthClient(auth_mod))

    out = auth_routes.verify_token("Bearer abc")
    assert out["user_id"] == "uid"

    with pytest.raises(HTTPException) as exc:
        auth_routes.verify_token("abc")
    assert exc.value.status_code == 401

    auth_mod.get_user_result = Obj(user=None)
    with pytest.raises(HTTPException):
        auth_routes.verify_token("Bearer abc")

    auth_mod.get_user_error = RuntimeError("boom")
    with pytest.raises(HTTPException):
        auth_routes.verify_token("Bearer abc")
