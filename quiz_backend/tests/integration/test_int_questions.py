"""Integration tests for /questions/* endpoints."""
import pytest
from tests.integration.conftest import USER_ID

# ── Fixtures ───────────────────────────────────────────────────────────────────

MCQ_PAYLOAD = {
    "topic_id": 1,
    "text": "What is the powerhouse of the cell?",
    "type": "MCQ",
    "options": {"A": "Nucleus", "B": "Mitochondria", "C": "Ribosome", "D": "Membrane"},
    "answer": "B",
    "difficulty": 2,
}

SHORT_PAYLOAD = {
    "topic_id": 1,
    "text": "Name the process plants use to make food.",
    "type": "SHORT",
    "options": None,
    "answer": "Photosynthesis",
    "keywords": ["photosynthesis"],
    "difficulty": 1,
}

_CREATED_QUESTION = {
    "id": 10,
    "topic_id": 1,
    "text": "What is the powerhouse of the cell?",
    "type": "MCQ",
    "options": {"A": "Nucleus", "B": "Mitochondria", "C": "Ribosome", "D": "Membrane"},
    "answer": "B",
    "difficulty": 2,
    "created_by": USER_ID,
    "irt_a": 1.0, "irt_b": -1.0, "irt_c": 0.25,
    "n_responses": 0, "n_correct": 0, "is_calibrated": False,
    "image_url": None,
}

_NEW_QUESTION = {
    "id": 5,
    "topic_id": 1,
    "text": "What is the powerhouse of the cell?",
    "type": "MCQ",
    "options": {"A": "Nucleus", "B": "Mitochondria", "C": "Ribosome", "D": "Membrane"},
    "difficulty": 2,
    "irt_a": 1.0,
    "irt_b": 0.0,
    "irt_c": 0.25,
    "created_by": USER_ID,
    "n_responses": 0,
    "n_correct": 0,
    "is_calibrated": False,
    "answer": "B",
}


# ── POST /questions/create ─────────────────────────────────────────────────────

class TestCreateQuestion:
    def test_mcq_created_successfully(self, client, auth_headers, make_db):
        make_db({
            ("questions", "insert"): [{"data": [_CREATED_QUESTION]}]
        })

        r = client.post("/questions/create", json=MCQ_PAYLOAD, headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["question"]["type"] == "MCQ"
        assert body["question"]["answer"] == "B"

    def test_short_question_created(self, client, auth_headers, make_db):
        created = {**_CREATED_QUESTION, "type": "SHORT", "answer": "Photosynthesis",
                   "options": None, "keywords": ["photosynthesis"]}
        make_db({("questions", "insert"): [{"data": [created]}]})

        r = client.post("/questions/create", json=SHORT_PAYLOAD, headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["question"]["type"] == "SHORT"

    def test_invalid_type_returns_422(self, client, auth_headers, make_db):
        make_db({})
        bad = {**MCQ_PAYLOAD, "type": "ESSAY"}

        r = client.post("/questions/create", json=bad, headers=auth_headers)

        # FastAPI/Pydantic returns 422 for enum/type validation failures
        assert r.status_code in (400, 422)

    def test_db_insert_failure_returns_500(self, client, auth_headers, make_db):
        # Stub returns no data → route raises 500
        make_db({("questions", "insert"): [{"data": None}]})

        r = client.post("/questions/create", json=MCQ_PAYLOAD, headers=auth_headers)

        assert r.status_code == 500

    def test_requires_auth(self, client, no_auth):
        r = client.post("/questions/create", json=MCQ_PAYLOAD)
        assert r.status_code in (401, 403)


# ── PUT /questions/{id} ────────────────────────────────────────────────────────

class TestUpdateQuestion:
    def test_update_success(self, client, auth_headers, make_db):
        updated = {**_CREATED_QUESTION, "text": "Updated text"}
        make_db({
            ("questions", "select"): [
                # ownership check
                {"data": {"id": 10, "created_by": USER_ID, "answer": "B"}}
            ],
            ("questions", "update"): [{"data": [updated]}],
        })

        r = client.put("/questions/10", json=MCQ_PAYLOAD, headers=auth_headers)

        assert r.status_code == 200
        assert "updated" in r.json()["message"].lower()

    def test_update_not_found_returns_404(self, client, auth_headers, make_db):
        make_db({
            ("questions", "select"): [{"data": None}],
        })

        r = client.put("/questions/999", json=MCQ_PAYLOAD, headers=auth_headers)

        assert r.status_code == 404

    def test_update_forbidden_for_other_user(self, client, auth_headers, make_db):
        make_db({
            ("questions", "select"): [
                {"data": {"id": 10, "created_by": "other-user", "answer": "B"}}
            ],
        })

        r = client.put("/questions/10", json=MCQ_PAYLOAD, headers=auth_headers)

        assert r.status_code in (401, 403)


# ── GET /questions/irt ─────────────────────────────────────────────────────────

class TestGetNextQuestion:
    def test_returns_new_question_when_no_due(self, client, auth_headers, make_db):
        make_db({
            ("user_topic_theta", "select"): [{"data": [{"topic_id": 1, "theta": 0.0, "is_calibrated": False}]}],
            # 1st fsrs_cards select: due questions → empty
            ("fsrs_cards", "select"): [
                {"data": []},  # due query
                {"data": []},  # seen IDs query
            ],
            # questions selects: primary window + fallback both return the question
            ("questions", "select"): [
                {"data": [_NEW_QUESTION]},  # b-range window
            ],
        })

        r = client.get("/questions/irt", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == 5
        # Answer must be stripped before returning
        assert "answer" not in body

    def test_prioritises_due_question(self, client, auth_headers, make_db):
        due_q = {**_NEW_QUESTION, "id": 99, "irt_a": 1.0, "irt_b": 0.0}
        make_db({
            ("user_topic_theta", "select"): [{"data": []}],
            ("fsrs_cards", "select"): [
                {"data": [{"questions": due_q}]},  # due query
                {"data": []},                       # seen IDs query
            ],
        })

        r = client.get("/questions/irt", headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["id"] == 99

    def test_returns_404_when_no_questions(self, client, auth_headers, make_db):
        make_db({
            ("user_topic_theta", "select"): [{"data": []}],
            ("fsrs_cards", "select"): [
                {"data": []},
                {"data": []},
            ],
            ("questions", "select"): [
                {"data": []},  # b-range window empty
                {"data": []},  # fallback also empty
            ],
        })

        r = client.get("/questions/irt", headers=auth_headers)

        assert r.status_code == 404

    def test_requires_auth(self, client, no_auth):
        r = client.get("/questions/irt")
        assert r.status_code in (401, 403)


# ── GET /questions/due/count ───────────────────────────────────────────────────

class TestDueCount:
    def test_returns_count(self, client, auth_headers, make_db):
        # The route uses fsrs_cards with due filter and a count query
        make_db({
            ("fsrs_cards", "select"): [{"data": [
                {"question_id": 1},
                {"question_id": 2},
                {"question_id": 3},
            ], "count": 3}],
            ("questions", "select"): [{"data": [
                {"id": 1}, {"id": 2}, {"id": 3}
            ]}],
        })

        r = client.get("/questions/due/count", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert "due_count" in body or "total_available" in body
