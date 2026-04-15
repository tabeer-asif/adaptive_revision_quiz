import pytest
from fastapi import HTTPException

from app.routes import questions as q_routes
from app.schemas.questions import CreateQuestionRequest
from tests.conftest import StubSupabaseDB, FakeUser


def test_answers_differ_non_json_fallback():
    assert q_routes.answers_differ({1, 2}, {1, 2}) is False


def test_create_question_multi_mcq_paths_and_insert_fail(monkeypatch):
    monkeypatch.setitem(q_routes.VALIDATORS, "MULTI_MCQ", lambda payload: None)
    monkeypatch.setattr(q_routes, "default_grm_thresholds", lambda b: [b - 0.5, b + 0.5])

    payload_auto = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MULTI_MCQ",
        options={"A": "1", "B": "2"},
        answer=["A"],
        difficulty=2,
    )

    payload_sorted = payload_auto.model_copy(update={"irt_thresholds": [1.0, -1.0]})

    db = StubSupabaseDB({
        ("questions", "insert"): [
            {"data": [{"id": 1, "text": "Q"}]},
            {"data": [{"id": 2, "text": "Q2"}]},
            {"data": []},
        ]
    })
    monkeypatch.setattr(q_routes, "supabase_db", db)

    out1 = q_routes.create_question(payload_auto, user=FakeUser("u1"))
    out2 = q_routes.create_question(payload_sorted, user=FakeUser("u1"))
    assert out1["question"]["id"] == 1
    assert out2["question"]["id"] == 2

    with pytest.raises(HTTPException) as exc:
        q_routes.create_question(payload_auto, user=FakeUser("u1"))
    assert exc.value.status_code == 500


def test_update_question_extra_branches(monkeypatch):
    monkeypatch.setitem(q_routes.VALIDATORS, "MULTI_MCQ", lambda payload: None)
    monkeypatch.setattr(q_routes, "default_grm_thresholds", lambda b: [b - 0.5, b + 0.5])

    payload = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MULTI_MCQ",
        options={"A": "1", "B": "2"},
        answer=["A"],
        difficulty=2,
    )

    saved_multi = q_routes.VALIDATORS.pop("MULTI_MCQ")
    with pytest.raises(HTTPException):
        q_routes.update_question(1, payload, user=FakeUser("u1"))
    q_routes.VALIDATORS["MULTI_MCQ"] = saved_multi

    db_not_found = StubSupabaseDB({("questions", "select"): [{"data": None}]})
    monkeypatch.setattr(q_routes, "supabase_db", db_not_found)
    with pytest.raises(HTTPException) as exc:
        q_routes.update_question(1, payload, user=FakeUser("u1"))
    assert exc.value.status_code == 404


def test_update_question_multi_mcq_sorted_thresholds(monkeypatch):
    monkeypatch.setitem(q_routes.VALIDATORS, "MULTI_MCQ", lambda payload: None)

    payload = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MULTI_MCQ",
        options={"A": "1", "B": "2"},
        answer=["A"],
        difficulty=2,
        irt_thresholds=[1.0, -1.0],
    )

    db = StubSupabaseDB({
        ("questions", "select"): [{"data": {"id": 1, "created_by": "u1", "answer": ["A"]}}],
        ("questions", "update"): [{"data": [{"id": 1, "text": "Q"}]}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db)

    out = q_routes.update_question(1, payload, user=FakeUser("u1"))
    assert out["question"]["id"] == 1
    assert db.last_payloads[("questions", "update")]["irt_thresholds"] == [-1.0, 1.0]


def test_update_question_multi_mcq_auto_thresholds(monkeypatch):
    monkeypatch.setitem(q_routes.VALIDATORS, "MULTI_MCQ", lambda payload: None)
    monkeypatch.setattr(q_routes, "default_grm_thresholds", lambda b: [b - 0.5, b + 0.5])

    payload = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MULTI_MCQ",
        options={"A": "1", "B": "2"},
        answer=["A"],
        difficulty=2,
        irt_thresholds=None,
        irt_b=None,
    )

    db = StubSupabaseDB({
        ("questions", "select"): [{"data": {"id": 1, "created_by": "u1", "answer": ["A"]}}],
        ("questions", "update"): [{"data": [{"id": 1, "text": "Q"}]}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db)

    out = q_routes.update_question(1, payload, user=FakeUser("u1"))
    assert out["question"]["id"] == 1
    assert db.last_payloads[("questions", "update")]["irt_thresholds"] == [-1.5, -0.5]

    db_no_update = StubSupabaseDB({
        ("questions", "select"): [{"data": {"id": 1, "created_by": "u1", "answer": ["A"]}}],
        ("questions", "update"): [{"data": []}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db_no_update)
    with pytest.raises(HTTPException) as exc:
        q_routes.update_question(1, payload, user=FakeUser("u1"))
    assert exc.value.status_code == 404


def test_get_next_question_by_topics_not_found_cases(monkeypatch):
    req = type("Req", (), {"topics": [1]})

    db_none = StubSupabaseDB({
        ("user_topic_theta", "select"): [{"data": []}],
        ("fsrs_cards", "select"): [{"data": []}, {"data": []}],
        ("questions", "select"): [{"data": []}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db_none)
    with pytest.raises(HTTPException) as exc:
        q_routes.get_next_question_by_topics(req, user=FakeUser("u1"))
    assert exc.value.status_code == 404

    db_some = StubSupabaseDB({
        ("user_topic_theta", "select"): [{"data": []}],
        ("fsrs_cards", "select"): [{"data": []}, {"data": []}],
        ("questions", "select"): [{"data": [{"id": 9, "topic_id": 1, "type": "MCQ", "answer": "A"}]}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db_some)
    monkeypatch.setattr(q_routes, "select_best_question_per_topic", lambda *args, **kwargs: None)
    with pytest.raises(HTTPException) as exc:
        q_routes.get_next_question_by_topics(req, user=FakeUser("u1"))
    assert exc.value.status_code == 404


def test_delete_all_and_delete_one_error_paths(monkeypatch):
    db_all_none = StubSupabaseDB({("questions", "select"): [{"data": []}]})
    monkeypatch.setattr(q_routes, "supabase_db", db_all_none)
    out = q_routes.delete_all_questions(user=FakeUser("u1"))
    assert out["deleted_count"] == 0

    db_q_missing = StubSupabaseDB({("questions", "select"): [{"data": None}]})
    monkeypatch.setattr(q_routes, "supabase_db", db_q_missing)
    with pytest.raises(HTTPException) as exc:
        q_routes.delete_question(1, user=FakeUser("u1"))
    assert exc.value.status_code == 404

    db_not_owner = StubSupabaseDB({("questions", "select"): [{"data": {"id": 1, "created_by": "u2"}}]})
    monkeypatch.setattr(q_routes, "supabase_db", db_not_owner)
    with pytest.raises(HTTPException) as exc:
        q_routes.delete_question(1, user=FakeUser("u1"))
    assert exc.value.status_code == 403

    db_delete_empty = StubSupabaseDB({
        ("questions", "select"): [{"data": {"id": 1, "created_by": "u1"}}],
        ("fsrs_cards", "delete"): [{"data": []}],
        ("questions", "delete"): [{"data": []}],
    })
    monkeypatch.setattr(q_routes, "supabase_db", db_delete_empty)
    with pytest.raises(HTTPException) as exc:
        q_routes.delete_question(1, user=FakeUser("u1"))
    assert exc.value.status_code == 404
