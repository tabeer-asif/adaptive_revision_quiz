"""Integration tests for /topics endpoints."""
import pytest


class TestGetTopics:
    def test_returns_topic_list(self, client, auth_headers, make_db):
        make_db({
            ("topics", "select"): [{"data": [
                {"id": 1, "name": "Biology"},
                {"id": 2, "name": "Chemistry"},
            ]}]
        })

        r = client.get("/topics", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert len(body) == 2
        assert body[0]["name"] == "Biology"

    def test_returns_empty_list_when_no_topics(self, client, auth_headers, make_db):
        make_db({("topics", "select"): [{"data": []}]})

        r = client.get("/topics", headers=auth_headers)

        assert r.status_code == 200
        assert r.json() == []

    def test_requires_auth(self, client, no_auth):
        r = client.get("/topics")
        assert r.status_code in (401, 403)


class TestCreateTopic:
    def test_creates_topic_successfully(self, client, auth_headers, make_db):
        make_db({
            # 1st select: duplicate check → empty
            ("topics", "select"): [{"data": []}],
            # insert → returns new row
            ("topics", "insert"): [{"data": [{"id": 3, "name": "Physics"}]}],
        })

        r = client.post("/topics", json={"name": "Physics"}, headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["name"] == "Physics"

    def test_rejects_empty_name(self, client, auth_headers, make_db):
        make_db({})

        r = client.post("/topics", json={"name": "   "}, headers=auth_headers)

        assert r.status_code == 400

    def test_rejects_duplicate_name(self, client, auth_headers, make_db):
        make_db({
            ("topics", "select"): [{"data": [{"id": 1, "name": "Biology"}]}],
        })

        r = client.post("/topics", json={"name": "Biology"}, headers=auth_headers)

        assert r.status_code == 409
        assert "exists" in r.json()["detail"].lower()

    def test_requires_auth(self, client, no_auth):
        r = client.post("/topics", json={"name": "Test"})
        assert r.status_code in (401, 403)
