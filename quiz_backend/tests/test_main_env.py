import importlib

import app.main as main_module


"""Tests for CORS origin selection from environment variables."""

# Convention: tests below follow Arrange / Act / Assert flow.


def test_main_uses_frontend_origins_env(monkeypatch):
    # Comma-separated env var should be split/trimmed into a list.
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    mod = importlib.reload(main_module)
    assert mod.allowed_origins == ["https://a.example", "https://b.example"]


def test_main_uses_single_frontend_origin_env(monkeypatch):
    # Single-origin fallback should be used when multi-origin is absent.
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://single.example")
    mod = importlib.reload(main_module)
    assert mod.allowed_origins == ["https://single.example"]
