import pytest
from fastapi import HTTPException

from app.routes import topics as topics_routes
from app.schemas.quiz import CreateTopicRequest
from tests.conftest import StubSupabaseDB, FakeUser


def test_get_topics_success_and_error(monkeypatch):
    db = StubSupabaseDB({("topics", "select"): [{"data": [{"id": 1, "name": "Math"}]}]})
    monkeypatch.setattr(topics_routes, "supabase_db", db)

    out = topics_routes.get_topics(user=FakeUser("u1"))
    assert out[0]["name"] == "Math"

    class BoomDB(StubSupabaseDB):
        def table(self, name):
            raise RuntimeError("db fail")

    monkeypatch.setattr(topics_routes, "supabase_db", BoomDB())
    with pytest.raises(HTTPException) as exc:
        topics_routes.get_topics(user=FakeUser("u1"))
    assert exc.value.status_code == 500


def test_create_topic_paths(monkeypatch):
    db = StubSupabaseDB({
        ("topics", "select"): [
            {"data": []},
            {"data": [{"id": 1}]},
            {"data": []},
        ],
        ("topics", "insert"): [
            {"data": [{"id": 2, "name": "Algebra"}]},
            {"data": []},
        ],
    })
    monkeypatch.setattr(topics_routes, "supabase_db", db)

    out = topics_routes.create_topic(CreateTopicRequest(name=" Algebra "), user=FakeUser("u1"))
    assert out["name"] == "Algebra"

    with pytest.raises(HTTPException) as exc:
        topics_routes.create_topic(CreateTopicRequest(name="Algebra"), user=FakeUser("u1"))
    assert exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc:
        topics_routes.create_topic(CreateTopicRequest(name=" "), user=FakeUser("u1"))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        topics_routes.create_topic(CreateTopicRequest(name="Geometry"), user=FakeUser("u1"))
    assert exc.value.status_code == 500
