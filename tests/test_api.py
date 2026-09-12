from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_shape(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "ping", lambda: {"database_name": "agentic_data_analyst", "version": "8.4"})
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
