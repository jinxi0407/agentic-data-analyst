from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_shape(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "ping", lambda: {"database_name": "agentic_data_analyst", "version": "8.4"})
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_query_endpoint_uses_production_result_shape(monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main,
        "run_question",
        lambda question: {
            "sql": "SELECT 1 LIMIT 200",
            "result": [{"value": 1}],
            "retry_count": 0,
            "latency_ms": 12.3,
            "trace": [{"stage": "execute", "status": "success"}],
            "status": "success",
        },
    )
    response = TestClient(app).post("/api/query", json={"question": "测试问题"})
    assert response.status_code == 200
    assert response.json()["engine"] == "Production NL2SQL Engine"
    assert response.json()["result"] == [{"value": 1}]
