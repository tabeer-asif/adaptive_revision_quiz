"""Integration tests for /analytics/* endpoints."""

from datetime import datetime, timedelta, timezone

import pytest


def test_theta_progression_returns_series(client, auth_headers, make_db):
    make_db(
        {
            ("review_logs", "select"): [
                {
                    "data": [
                        {
                            "topic_id": 1,
                            "theta_before": -0.2,
                            "theta_after": 0.1,
                            "posterior_sd": 0.82,
                            "created_at": "2026-05-01T10:00:00+00:00",
                        },
                        {
                            "topic_id": 1,
                            "theta_before": 0.1,
                            "theta_after": 0.25,
                            "posterior_sd": 0.74,
                            "created_at": "2026-05-03T10:00:00+00:00",
                        },
                    ]
                }
            ],
            ("topics", "select"): [{"data": [{"id": 1, "name": "Biology"}]}],
        }
    )

    res = client.get("/analytics/theta-progression", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert "series" in body
    assert len(body["series"]) == 1
    assert body["series"][0]["topic_name"] == "Biology"
    assert body["series"][0]["points"][0]["theta_before"] == -0.2
    assert body["series"][0]["points"][0]["posterior_sd"] == 0.82


def test_topic_summary_returns_theta_and_response_count(client, auth_headers, make_db):
    make_db(
        {
            ("user_topic_theta", "select"): [
                {
                    "data": [
                        {
                            "topic_id": 2,
                            "theta": 0.55,
                            "n_responses": 14,
                            "theta_variance": 0.42,
                            "is_calibrated": False,
                            "last_updated": "2026-05-05T10:00:00+00:00",
                        }
                    ]
                }
            ],
            ("topics", "select"): [{"data": [{"id": 2, "name": "Chemistry"}]}],
        }
    )

    res = client.get("/analytics/topic-summary", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert len(body["topics"]) == 1
    assert body["topics"][0]["theta"] == 0.55
    assert body["topics"][0]["n_responses"] == 14


def test_fsrs_retention_returns_due_and_stability_trends(client, auth_headers, make_db):
    due_1 = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    due_2 = (datetime.now(timezone.utc) + timedelta(days=1, hours=3)).isoformat()
    due_3 = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    make_db(
        {
            ("fsrs_cards", "select"): [
                {
                    "data": [
                        {
                            "due": due_1,
                            "stability": 3.2,
                            "questions": {"topic_id": 1, "created_by": "user-1"},
                        },
                        {
                            "due": due_2,
                            "stability": 4.0,
                            "questions": {"topic_id": 2, "created_by": "user-1"},
                        },
                        {
                            "due": due_3,
                            "stability": 2.0,
                            "questions": {"topic_id": 2, "created_by": "user-1"},
                        },
                    ]
                }
            ]
        }
    )

    res = client.get("/analytics/fsrs-retention", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert "summary" in body
    assert "due_counts_over_time" in body
    assert "stability_trend" in body
    assert len(body["due_counts_over_time"]) >= 1
    assert len(body["stability_trend"]) >= 1


def test_question_performance_returns_pass_rate_and_irt_b_drift(client, auth_headers, make_db):
    make_db(
        {
            ("questions", "select"): [
                {
                    "data": [
                        {
                            "id": 11,
                            "topic_id": 1,
                            "text": "What is ATP?",
                            "irt_b": 0.4,
                            "n_responses": 0,
                            "n_correct": 0,
                        }
                    ]
                }
            ],
            ("review_logs", "select"): [
                {
                    "data": [
                        {"question_id": 11, "correct": True, "created_at": "2026-05-01T10:00:00+00:00"},
                        {"question_id": 11, "correct": False, "created_at": "2026-05-02T10:00:00+00:00"},
                        {"question_id": 11, "correct": True, "created_at": "2026-05-03T10:00:00+00:00"},
                    ]
                }
            ],
        }
    )

    res = client.get("/analytics/question-performance", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert len(body["questions"]) == 1
    row = body["questions"][0]
    assert row["attempts"] == 3
    assert row["pass_rate"] == pytest.approx(2 / 3)
    assert row["irt_b"] == 0.4
    assert row["irt_b_drift"] is not None


@pytest.mark.parametrize(
    "path",
    [
        "/analytics/theta-progression",
        "/analytics/topic-summary",
        "/analytics/fsrs-retention",
        "/analytics/question-performance",
    ],
)
def test_analytics_endpoints_require_auth(client, no_auth, path):
    res = client.get(path)
    assert res.status_code in (401, 403)
