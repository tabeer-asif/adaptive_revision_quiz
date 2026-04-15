from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_health_message():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["message"] == "Adaptive Quiz Engine Backend Running!"
