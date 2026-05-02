from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes import quiz as quiz_routes
from app.schemas.quiz import SubmitAnswerRequest
from tests.conftest import StubSupabaseDB, FakeUser


"""Branch-completion tests for submit-answer across question types."""

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


def _patch_common(monkeypatch):
    # Shared patches for dependencies that are irrelevant to branch intent.
    monkeypatch.setattr(quiz_routes, "scheduler", FakeScheduler())
    monkeypatch.setattr(quiz_routes, "Card", FakeCard)
    monkeypatch.setattr(quiz_routes, "State", lambda v: SimpleNamespace(value=v))
    monkeypatch.setattr(quiz_routes, "validate_question_exists", lambda resp: None)
    monkeypatch.setattr(quiz_routes, "validate_answer_submitted", lambda selected: None)


def test_submit_answer_multi_mcq_threshold_paths(monkeypatch):
    # Covers MULTI_MCQ branches: 2PL fallback and GRM category transitions.
    _patch_common(monkeypatch)
    monkeypatch.setattr(quiz_routes, "validate_multi_mcq_selection", lambda selected, options: ["A", "B"])
    monkeypatch.setattr(quiz_routes, "validate_multi_mcq_db_answer", lambda ans: ["A", "C"])

    # score=0.4 -> fallback 2PL branch when thresholds missing
    monkeypatch.setattr(quiz_routes, "score_multi_mcq", lambda selected, correct: 0.4)
    monkeypatch.setattr(quiz_routes, "get_fsrs_rating", lambda *args, **kwargs: SimpleNamespace(value=1))
    monkeypatch.setattr(quiz_routes, "update_theta_2pl", lambda theta, a, b, signal, lr: theta + 0.1)

    db = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 10,
            "topic_id": 3,
            "type": "MULTI_MCQ",
            "answer": ["A", "C"],
            "options": {"A": "1", "B": "2", "C": "3"},
            "irt_a": 1.0,
            "irt_b": 0.0,
            "irt_thresholds": None,
            "n_responses": 0,
            "n_correct": 0,
        }]}],
        ("fsrs_cards", "select"): [{"data": []}],
        ("fsrs_cards", "upsert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "select"): [{"data": []}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 3}]}],
        ("questions", "update"): [{"data": [{"id": 10}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db)

    out = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=10, selected_option=["A", "B"], response_time=5.0),
        user=FakeUser("u1"),
    )
    assert "next_review" in out

    # score=0.6 with thresholds present -> GRM branch, category=1
    monkeypatch.setattr(quiz_routes, "score_multi_mcq", lambda selected, correct: 0.6)
    monkeypatch.setattr(quiz_routes, "update_theta_grm", lambda theta, a, thresholds, cat, lr: theta + 0.2)

    db2 = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 11,
            "topic_id": 3,
            "type": "MULTI_MCQ",
            "answer": ["A", "C"],
            "options": {"A": "1", "B": "2", "C": "3"},
            "irt_a": 1.0,
            "irt_b": 0.0,
            "irt_thresholds": [-0.5, 0.5],
            "n_responses": 0,
            "n_correct": 0,
        }]}],
        ("fsrs_cards", "select"): [{"data": []}],
        ("fsrs_cards", "upsert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "select"): [{"data": []}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 3}]}],
        ("questions", "update"): [{"data": [{"id": 11}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db2)

    out2 = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=11, selected_option=["A", "B"], response_time=5.0),
        user=FakeUser("u1"),
    )
    assert "next_review" in out2

    # score=0.2 with thresholds present -> GRM branch, category=0
    monkeypatch.setattr(quiz_routes, "score_multi_mcq", lambda selected, correct: 0.2)

    db3 = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 12,
            "topic_id": 3,
            "type": "MULTI_MCQ",
            "answer": ["A", "C"],
            "options": {"A": "1", "B": "2", "C": "3"},
            "irt_a": 1.0,
            "irt_b": 0.0,
            "irt_thresholds": [-0.5, 0.5],
            "n_responses": 0,
            "n_correct": 0,
        }]}],
        ("fsrs_cards", "select"): [{"data": []}],
        ("fsrs_cards", "upsert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "select"): [{"data": []}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 3}]}],
        ("questions", "update"): [{"data": [{"id": 12}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db3)

    out3 = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=12, selected_option=["A", "B"], response_time=5.0),
        user=FakeUser("u1"),
    )
    assert "next_review" in out3


def test_submit_answer_numeric_short_open_and_existing_card(monkeypatch):
    # Covers NUMERIC/SHORT/OPEN branches plus existing card/theta paths.
    _patch_common(monkeypatch)

    monkeypatch.setattr(quiz_routes, "validate_numeric_selection", lambda s: 10.0)
    monkeypatch.setattr(quiz_routes, "validate_numeric_db_answer", lambda a: 10.0)
    monkeypatch.setattr(quiz_routes, "validate_numeric_tolerance", lambda t: 0.0)
    monkeypatch.setattr(quiz_routes, "score_numeric", lambda user, correct, tol: 1.0)
    monkeypatch.setattr(quiz_routes, "get_fsrs_rating", lambda *args, **kwargs: SimpleNamespace(value=4))
    monkeypatch.setattr(quiz_routes, "update_theta_2pl", lambda theta, a, b, signal, lr: theta + 0.3)

    existing_due = datetime.now(timezone.utc).isoformat()
    db = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 20,
            "topic_id": 9,
            "type": "NUMERIC",
            "answer": 10.0,
            "options": None,
            "tolerance": 0.0,
            "irt_a": 1.0,
            "irt_b": 0.0,
            "n_responses": 9,
            "n_correct": 5,
        }]}],
        ("fsrs_cards", "select"): [{"data": [{
            "stability": 1.0,
            "difficulty": 4.0,
            "due": existing_due,
            "last_review": existing_due,
            "state": 1,
            "step": 1,
        }]}],
        ("fsrs_cards", "upsert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "select"): [{"data": [{"theta": 0.1, "theta_variance": 0.8, "n_responses": 10, "is_calibrated": False}]}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 9}]}],
        ("questions", "update"): [{"data": [{"id": 20}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db)

    out = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=20, selected_option=10.0, response_time=3.0),
        user=FakeUser("u1"),
    )
    assert out["correct"] is True
    updates = db.last_payloads[("questions", "update")]
    assert "irt_b" in updates

    monkeypatch.setattr(quiz_routes, "validate_short_text", lambda s: "student text")
    monkeypatch.setattr(quiz_routes, "score_short", lambda submitted, keywords, model: (True, 0.8))

    db_short = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 21,
            "topic_id": 9,
            "type": "SHORT",
            "answer": "model",
            "keywords": ["k1", "k2"],
            "options": None,
            "irt_a": 1.0,
            "irt_b": 0.0,
            "n_responses": 0,
            "n_correct": 0,
        }]}],
        ("fsrs_cards", "select"): [{"data": []}],
        ("fsrs_cards", "upsert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "select"): [{"data": []}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 9}]}],
        ("questions", "update"): [{"data": [{"id": 21}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db_short)

    out_short = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=21, selected_option="some answer", response_time=6.0),
        user=FakeUser("u1"),
    )
    assert out_short["correct"] is True

    monkeypatch.setattr(quiz_routes, "Rating", lambda r: SimpleNamespace(value=r))
    monkeypatch.setattr(quiz_routes, "validate_open_text", lambda s, r, require_rating=True: "open answer")

    db_open = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 22,
            "topic_id": 9,
            "type": "OPEN",
            "answer": "rubric",
            "options": None,
            "irt_a": 1.0,
            "irt_b": 0.0,
            "n_responses": 0,
            "n_correct": 0,
        }]}],
        ("fsrs_cards", "select"): [{"data": []}],
        ("fsrs_cards", "upsert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "select"): [{"data": []}],
        ("review_logs", "insert"): [{"data": [{"id": 1}]}],
        ("user_topic_theta", "upsert"): [{"data": [{"topic_id": 9}]}],
        ("questions", "update"): [{"data": [{"id": 22}]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db_open)

    out_open = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=22, selected_option="reflection", response_time=10.0, self_rating=2),
        user=FakeUser("u1"),
    )
    assert out_open["correct"] is False


def test_submit_open_answer_without_rating_returns_preview(monkeypatch):
    # OPEN questions can return model answer first, then wait for a self-rating.
    _patch_common(monkeypatch)
    monkeypatch.setattr(quiz_routes, "validate_open_text", lambda s, r, require_rating=True: "open answer")

    db_open = StubSupabaseDB({
        ("questions", "select"): [{"data": [{
            "id": 30,
            "topic_id": 9,
            "type": "OPEN",
            "answer": "Use key steps and vocabulary.",
            "options": None,
            "irt_a": 1.0,
            "irt_b": 0.0,
            "n_responses": 0,
            "n_correct": 0,
        }]}],
    })
    monkeypatch.setattr(quiz_routes, "supabase_db", db_open)

    out = quiz_routes.submit_answer(
        SubmitAnswerRequest(question_id=30, selected_option="my response", response_time=8.0),
        user=FakeUser("u1"),
    )

    assert out["requires_self_rating"] is True
    assert out["correct_answer"] == "Use key steps and vocabulary."
