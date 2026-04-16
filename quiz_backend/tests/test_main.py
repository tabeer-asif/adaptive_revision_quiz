from fastapi.testclient import TestClient

from app.main import app


"""Smoke test for FastAPI app wiring."""

# Convention: tests below follow Arrange / Act / Assert flow.


client = TestClient(app)


def test_root_health_message():
    # Basic health endpoint should always return JSON and status 200.
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["message"] == "Adaptive Quiz Engine Backend Running!"
