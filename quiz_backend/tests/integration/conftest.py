"""
Shared fixtures for integration tests.

Every test in this package gets:
  - `client`        : FastAPI TestClient with get_current_user overridden to FakeUser("user-1")
  - `auth_headers`  : {"Authorization": "Bearer test-token"} convenience dict
  - `make_db`       : factory that returns a pre-scripted StubSupabaseDB and patches all
                      route modules that import supabase_db in one call

Auth routes use `supabase_auth` directly; tests that exercise those routes
monkeypatch `app.routes.auth.supabase_auth` themselves.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies.auth import get_current_user
from tests.conftest import FakeUser, StubSupabaseDB

USER_ID = "user-1"

# ── App-level auth override ────────────────────────────────────────────────────
def _fake_user():
    return FakeUser(USER_ID)


@pytest.fixture(autouse=True)
def override_auth():
    """Install fake user override for every test, then remove it cleanly."""
    app.dependency_overrides[get_current_user] = _fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def no_auth():
    """
    Remove the auth override so requests without a valid header get 403.
    Use on tests that verify authentication is enforced.
    Autouse `override_auth` runs first (installs), then this fixture pops it.
    """
    app.dependency_overrides.pop(get_current_user, None)
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-token"}


# ── DB patching helper ─────────────────────────────────────────────────────────
_DB_MODULE_PATHS = [
    "app.routes.questions",
    "app.routes.quiz",
    "app.routes.topics",
    "app.routes.uploads",
    "app.routes.ai",
    "app.routes.explanations",
    "app.routes.analytics",
    "app.dependencies.question_validators",  # also imports supabase_db at module level
]


@pytest.fixture()
def make_db(monkeypatch):
    """
    Returns a factory: `make_db(scripted_dict)` → StubSupabaseDB.
    The stub is patched into every route module that uses supabase_db,
    so a single DB object services the whole request lifecycle.
    """
    def _factory(scripted=None):
        db = StubSupabaseDB(scripted or {})
        for mod_path in _DB_MODULE_PATHS:
            import importlib
            mod = importlib.import_module(mod_path)
            monkeypatch.setattr(mod, "supabase_db", db)
        return db

    return _factory
