import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.dependencies import auth as auth_dep
from tests.conftest import FakeSupabaseAuthClient, FakeAuthModule


"""Unit tests for auth dependency token verification."""

# Convention: tests below follow Arrange / Act / Assert flow.


class UserResp:
    def __init__(self, user):
        self.user = user


class User:
    def __init__(self, user_id):
        self.id = user_id


def test_get_current_user_success(monkeypatch):
    # Valid token should return a user object from Supabase auth.
    mod = FakeAuthModule()
    mod.get_user_result = UserResp(User("u1"))
    monkeypatch.setattr(auth_dep, "supabase_auth", FakeSupabaseAuthClient(mod))

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    user = auth_dep.get_current_user(creds)
    assert user.id == "u1"


def test_get_current_user_invalid(monkeypatch):
    # Missing user in auth response should map to 401.
    mod = FakeAuthModule()
    mod.get_user_result = UserResp(None)
    monkeypatch.setattr(auth_dep, "supabase_auth", FakeSupabaseAuthClient(mod))

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with pytest.raises(HTTPException) as exc:
        auth_dep.get_current_user(creds)
    assert exc.value.status_code == 401


def test_get_current_user_exception(monkeypatch):
    # Any client exception should be normalized to 401.
    mod = FakeAuthModule()
    mod.get_user_error = RuntimeError("boom")
    monkeypatch.setattr(auth_dep, "supabase_auth", FakeSupabaseAuthClient(mod))

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with pytest.raises(HTTPException) as exc:
        auth_dep.get_current_user(creds)
    assert exc.value.status_code == 401
