"""Integration tests for /quiz/submit-answer endpoint.

Each test scripts the DB in the order the route actually calls it:
  1. questions.select    — fetch the question
  2. fsrs_cards.select   — fetch existing card (or empty → new Card())
  3. fsrs_cards.upsert   — save updated card  (write; return ignored)
  4. user_topic_theta.select — fetch current theta
  5. review_logs.insert  — write log          (return ignored)
  6. user_topic_theta.upsert — save theta     (return ignored)
  7. questions.update    — update calibration (return ignored)
"""
import pytest
from tests.integration.conftest import USER_ID
from datetime import datetime, timezone


def _iso_future():
    return (datetime.now(timezone.utc).isoformat())


_BASE_QUESTION = {
    "id": 1,
    "topic_id": 10,
    "type": "MCQ",
    "text": "What is 2+2?",
    "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
    "answer": "B",
    "difficulty": 2,
    "irt_a": 1.0,
    "irt_b": 0.0,
    "irt_c": 0.25,
    "irt_thresholds": None,
    "tolerance": None,
    "keywords": None,
    "n_responses": 0,
    "n_correct": 0,
    "created_by": USER_ID,
}

_THETA_ROW = {
    "user_id": USER_ID,
    "topic_id": 10,
    "theta": 0.0,
    "theta_variance": 1.0,
    "n_responses": 5,
    "is_calibrated": False,
}

_FSRS_CARD = {
    "user_id": USER_ID,
    "question_id": 1,
    "stability": 1.0,
    "difficulty": 5.0,
    "due": _iso_future(),
    "last_review": _iso_future(),
    "state": 1,
    "step": 0,
}


def _submit(client, auth_headers, payload):
    return client.post("/quiz/submit-answer", json=payload, headers=auth_headers)


def _scripted_for_question(question, existing_card=None):
    card_data = [existing_card] if existing_card else []
    return {
        ("questions", "select"): [{"data": [question]}],
        ("fsrs_cards", "select"): [{"data": card_data}],
        ("user_topic_theta", "select"): [{"data": [_THETA_ROW]}],
    }


class TestSubmitMCQ:
    def test_correct_answer(self, client, auth_headers, make_db):
        make_db(_scripted_for_question(_BASE_QUESTION))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": "B",
            "response_time": 5.0,
        })

        assert r.status_code == 200
        body = r.json()
        assert body["correct"] is True
        assert "correct_answer" in body

    def test_wrong_answer(self, client, auth_headers, make_db):
        make_db(_scripted_for_question(_BASE_QUESTION))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": "A",
            "response_time": 4.0,
        })

        assert r.status_code == 200
        assert r.json()["correct"] is False

    def test_uses_existing_fsrs_card(self, client, auth_headers, make_db):
        make_db(_scripted_for_question(_BASE_QUESTION, existing_card=_FSRS_CARD))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": "B",
            "response_time": 3.0,
        })

        assert r.status_code == 200

    def test_question_not_found_returns_404(self, client, auth_headers, make_db):
        make_db({("questions", "select"): [{"data": []}]})

        r = _submit(client, auth_headers, {
            "question_id": 999,
            "selected_option": "A",
            "response_time": 2.0,
        })

        assert r.status_code == 404

    def test_requires_auth(self, client, no_auth):
        r = client.post("/quiz/submit-answer", json={
            "question_id": 1, "selected_option": "A", "response_time": 1.0
        })
        assert r.status_code in (401, 403)


class TestSubmitNUMERIC:
    def test_correct_within_tolerance(self, client, auth_headers, make_db):
        q = {**_BASE_QUESTION, "type": "NUMERIC", "answer": 9.81,
             "tolerance": 0.1, "options": None, "irt_c": None}
        make_db(_scripted_for_question(q))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": 9.82,
            "response_time": 6.0,
        })

        assert r.status_code == 200
        assert r.json()["correct"] is True

    def test_wrong_outside_tolerance(self, client, auth_headers, make_db):
        q = {**_BASE_QUESTION, "type": "NUMERIC", "answer": 9.81,
             "tolerance": 0.1, "options": None, "irt_c": None}
        make_db(_scripted_for_question(q))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": 5.0,
            "response_time": 6.0,
        })

        assert r.status_code == 200
        assert r.json()["correct"] is False


class TestSubmitSHORT:
    def test_keyword_match(self, client, auth_headers, make_db):
        q = {**_BASE_QUESTION, "type": "SHORT", "answer": "photosynthesis",
             "keywords": ["photosynthesis"], "options": None, "irt_c": None}
        make_db(_scripted_for_question(q))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": "Photosynthesis",
            "response_time": 8.0,
        })

        assert r.status_code == 200
        assert r.json()["correct"] is True


class TestSubmitOPEN:
    def test_first_call_returns_model_answer(self, client, auth_headers, make_db):
        q = {**_BASE_QUESTION, "type": "OPEN", "answer": "Plants convert light to energy.",
             "options": None, "irt_c": None, "keywords": None}
        make_db(_scripted_for_question(q))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": "My answer",
            "response_time": 20.0,
            # No self_rating → triggers model answer return
        })

        assert r.status_code == 200
        body = r.json()
        assert body.get("requires_self_rating") is True
        assert "correct_answer" in body

    def test_with_self_rating_completes_submission(self, client, auth_headers, make_db):
        q = {**_BASE_QUESTION, "type": "OPEN", "answer": "Plants convert light to energy.",
             "options": None, "irt_c": None, "keywords": None}
        make_db(_scripted_for_question(q))

        r = _submit(client, auth_headers, {
            "question_id": 1,
            "selected_option": "My answer",
            "response_time": 20.0,
            "self_rating": 3,
        })

        assert r.status_code == 200
        body = r.json()
        assert "correct" in body
        assert body["correct"] is True  # self_rating 3 >= 3 → correct
