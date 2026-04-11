from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "snowflake" in data
    assert "gemini" in data
    assert "embeddings" in data
    assert "timestamp" in data


def test_chat_rejects_empty_message():
    response = client.post("/chat", json={"message": "", "session_id": "test"})
    assert response.status_code == 400
