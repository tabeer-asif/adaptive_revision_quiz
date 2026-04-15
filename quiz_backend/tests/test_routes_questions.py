import pytest
from fastapi import HTTPException

from app.routes import questions as q_routes
from app.schemas.questions import CreateQuestionRequest, BulkDeleteRequest
from tests.conftest import StubSupabaseDB, FakeUser


def test_helpers_and_answers_differ():
    assert q_routes.get_irt_defaults(1)["irt_b"] == -1.0
    assert q_routes.get_irt_defaults(4)["irt_b"] == 1.0
    assert q_routes.answers_differ({"a": 1}, {"a": 1}) is False
    assert q_routes.answers_differ({"a": 1}, {"a": 2}) is True


def test_create_question_success(monkeypatch):
    monkeypatch.setitem(q_routes.VALIDATORS, "MCQ", lambda payload: None)
    monkeypatch.setattr(q_routes, "default_grm_thresholds", lambda b: [b - 0.5, b + 0.5])

    db = StubSupabaseDB({("questions", "insert"): [{"data": [{"id": 1, "text": "Q"}]}]})
    monkeypatch.setattr(q_routes, "supabase_db", db)

    payload = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MCQ",
        options={"A": "1", "B": "2"},
        answer="A",
        difficulty=2,
    )
    out = q_routes.create_question(payload, user=FakeUser("u1"))
    assert out["question"]["id"] == 1


def test_create_question_invalid_type(monkeypatch):
    payload = CreateQuestionRequest(topic_id=1, text="Q", type="OPEN", answer="x")
    monkeypatch.setitem(q_routes.VALIDATORS, "OPEN", lambda payload: None)
    q_routes.VALIDATORS.pop("OPEN")
    with pytest.raises(HTTPException):
        q_routes.create_question(payload, user=FakeUser("u1"))
    q_routes.VALIDATORS["OPEN"] = lambda payload: None


def test_update_question_paths(monkeypatch):
    monkeypatch.setitem(q_routes.VALIDATORS, "MCQ", lambda payload: None)
    monkeypatch.setattr(q_routes, "default_grm_thresholds", lambda b: [b - 0.5, b + 0.5])

    payload = CreateQuestionRequest(
        topic_id=1,
        text="New",
        type="MCQ",
        options={"A": "1", "B": "2"},
        answer="A",
        difficulty=3,
    )

    db = StubSupabaseDB({
        ("questions", "select"): [{"data": {"id": 1, "created_by": "u1", "answer": "B"}}],
        ("questions", "update"): [{"data": [{"id": 1, "text": "New"}]}],
        ("fsrs_cards", "delete"): [{"data": []}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db)

    out = q_routes.update_question(1, payload, user=FakeUser("u1"))
    assert out["question"]["id"] == 1

    db2 = StubSupabaseDB({("questions", "select"): [{"data": {"id": 1, "created_by": "u2", "answer": "A"}}]})
    monkeypatch.setattr(q_routes, "supabase_db", db2)
    with pytest.raises(HTTPException) as exc:
        q_routes.update_question(1, payload, user=FakeUser("u1"))
    assert exc.value.status_code == 403


def test_get_next_question_by_topics(monkeypatch):
    db = StubSupabaseDB({
        ("user_topic_theta", "select"): [{"data": [{"topic_id": 1, "theta": 0.2, "is_calibrated": True}]}],
        ("fsrs_cards", "select"): [
            {"data": [{"question_id": 10, "questions": {"id": 10, "topic_id": 1, "type": "MCQ", "answer": "A"}}]},
            {"data": [{"question_id": 10}]},
        ],
        ("questions", "select"): [{"data": []}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db)
    monkeypatch.setattr(q_routes, "select_best_question_per_topic", lambda theta_map, pool, target=None: dict(pool[0]))

    req = type("Req", (), {"topics": [1]})
    out = q_routes.get_next_question_by_topics(req, user=FakeUser("u1"))
    assert out["id"] == 10
    assert "answer" not in out


def test_overview_due_and_delete_flows(monkeypatch):
    db = StubSupabaseDB({
        ("questions", "select"): [
            {"data": [{"id": 1, "topic_id": 9, "text": "Q", "type": "MCQ", "difficulty": 1, "created_by": "u1", "answer": "A"}]},
            {"data": [{"id": 1}, {"id": 2}]},
            {"data": [{"id": 1, "created_by": "u1"}, {"id": 2, "created_by": "u1"}]},
            {"data": [{"id": 1, "created_by": "u1"}, {"id": 2, "created_by": "u1"}]},
            {"data": {"id": 1, "created_by": "u1"}},
        ],
        ("topics", "select"): [{"data": [{"id": 9, "name": "Math"}]}],
        ("fsrs_cards", "select"): [
            {"data": [{"question_id": 1, "due": "2026-01-01", "last_review": "2026-01-01"}]},
            {"data": [], "count": 1},
            {"data": [], "count": 1},
        ],
        ("fsrs_cards", "delete"): [{"data": []}, {"data": []}, {"data": []}],
        ("questions", "delete"): [{"data": [{"id": 1}, {"id": 2}]}, {"data": [{"id": 1}, {"id": 2}]}, {"data": [{"id": 1}]}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db)

    overview = q_routes.get_questions_overview(user=FakeUser("u1"))
    assert overview[0]["topic_name"] == "Math"
    assert overview[0]["answer"] == "A"

    due = q_routes.get_due_count(user=FakeUser("u1"))
    assert due["total_available"] >= 0

    delete_all = q_routes.delete_all_questions(user=FakeUser("u1"))
    assert delete_all["deleted_count"] == 2

    delete_many = q_routes.delete_questions(BulkDeleteRequest(ids=[1, 2]), user=FakeUser("u1"))
    assert delete_many["deleted_count"] == 2

    delete_one = q_routes.delete_question(1, user=FakeUser("u1"))
    assert "deleted successfully" in delete_one["message"]


def test_delete_questions_errors(monkeypatch):
    with pytest.raises(HTTPException):
        q_routes.delete_questions(BulkDeleteRequest(ids=[]), user=FakeUser("u1"))

    db_missing = StubSupabaseDB({("questions", "select"): [{"data": [{"id": 1, "created_by": "u1"}]}]})
    monkeypatch.setattr(q_routes, "supabase_db", db_missing)
    with pytest.raises(HTTPException) as exc:
        q_routes.delete_questions(BulkDeleteRequest(ids=[1, 2]), user=FakeUser("u1"))
    assert exc.value.status_code == 404

    db_owner = StubSupabaseDB({("questions", "select"): [{"data": [{"id": 1, "created_by": "u2"}]}]})
    monkeypatch.setattr(q_routes, "supabase_db", db_owner)
    with pytest.raises(HTTPException) as exc:
        q_routes.delete_questions(BulkDeleteRequest(ids=[1]), user=FakeUser("u1"))
    assert exc.value.status_code == 403
