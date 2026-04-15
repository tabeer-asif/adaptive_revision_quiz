import importlib

import app.main as main_module


def test_main_uses_frontend_origins_env(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    mod = importlib.reload(main_module)
    assert mod.allowed_origins == ["https://a.example", "https://b.example"]


def test_main_uses_single_frontend_origin_env(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://single.example")
    mod = importlib.reload(main_module)
    assert mod.allowed_origins == ["https://single.example"]
