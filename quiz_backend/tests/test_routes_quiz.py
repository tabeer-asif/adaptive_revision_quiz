from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routes import quiz as quiz_routes
from app.schemas.quiz import SubmitAnswerRequest
from tests.conftest import StubSupabaseDB, FakeUser


"""Route tests for quiz answer submission endpoint."""

# Convention: tests below follow Arrange / Act / Assert flow.


class FakeCard:
    # Minimal card object shape used by the submit flow.
    def __init__(self, **kwargs):
        now = datetime.now(timezone.utc)
        self.stability = kwargs.get("stability", 1.0)
        self.difficulty = kwargs.get("difficulty", 5.0)
        self.due = kwargs.get("due", now + timedelta(days=1))
        self.last_review = kwargs.get("last_review", now)
        self.state = kwargs.get("state", SimpleNamespace(value=1))
        self.step = kwargs.get("step", 0)


class FakeScheduler:
    # Deterministic scheduler to avoid time/interval variability in tests.
    def review_card(self, card, rating):
        card.due = datetime.now(timezone.utc) + timedelta(days=2)
        return card, 2


def test_submit_answer_mcq_success(monkeypatch):
    # End-to-end happy path for MCQ submission and persistence updates.
    db = StubSupabaseDB({
        ("questions", "select"): [
            {"data": [{
                "id": 7,
                "topic_id": 3,
                "type": "MCQ",
                "answer": "A",
                "options": {"A": "X", "B": "Y"},
                "irt_a": 1.0,
                "irt_b": 0.0,
                "irt_c": 0.25,
                "n_responses": 0,
                "n_correct": 0,
            }]}
        ],
        ("fsrs_cards", "select"): [{"data": []}],
        ("fsrs_cards", "upsert"): [{"data": [{"question_id": 7}]}],
        ("user_topic_theta", "select"): [{"data": []}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 3}]}],
        ("questions", "update"): [{"data": [{"id": 7}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db)
    monkeypatch.setattr(quiz_routes, "scheduler", FakeScheduler())
    monkeypatch.setattr(quiz_routes, "Card", FakeCard)
    monkeypatch.setattr(quiz_routes, "get_fsrs_rating", lambda *args, **kwargs: SimpleNamespace(value=3))
    monkeypatch.setattr(quiz_routes, "update_theta_3pl", lambda theta, a, b, c, response, learning_rate: theta + 0.2)

    request = SubmitAnswerRequest(question_id=7, selected_option="A", response_time=4.0)
    out = quiz_routes.submit_answer(request, user=FakeUser("u1"))

    assert out["correct"] is True
    assert "next_review" in out


def test_submit_answer_question_not_found(monkeypatch):
    # Missing question should raise 404.
    db = StubSupabaseDB({("questions", "select"): [{"data": []}]})
    monkeypatch.setattr(quiz_routes, "supabase_db", db)

    request = SubmitAnswerRequest(question_id=7, selected_option="A", response_time=4.0)
    with pytest.raises(HTTPException) as exc:
        quiz_routes.submit_answer(request, user=FakeUser("u1"))
    assert exc.value.status_code == 404


def test_submit_answer_unsupported_type(monkeypatch):
    # Unsupported question type should raise 400.
    db = StubSupabaseDB({
        ("questions", "select"): [
            {"data": [{
                "id": 7,
                "topic_id": 3,
                "type": "UNKNOWN",
                "answer": "A",
                "options": {},
            }]}
        ]
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db)

    request = SubmitAnswerRequest(question_id=7, selected_option="A", response_time=4.0)
    with pytest.raises(HTTPException) as exc:
        quiz_routes.submit_answer(request, user=FakeUser("u1"))
    assert exc.value.status_code == 400
