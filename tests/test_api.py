from fastapi.testclient import TestClient
import os

from backend.app import app

client = TestClient(app)


def test_health():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("ok") is True
