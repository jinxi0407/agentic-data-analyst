import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.agent import clarification as gate, production
from app.main import app


def output(clarify=False, kind="time"):
    return dict(decision="clarify" if clarify else "proceed",
                ambiguity_type=kind if clarify else "none", reason="业务口径已知" if not clarify else "时间未明确",
                clarification_question="你希望查看最近7天还是30天？" if clarify else "",
                resolved_question="")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(gate, "schema_context", lambda: "users.user_id = orders.user_id")


@pytest.mark.parametrize("question,ambiguous,kind", [
    ("上个月销售额是多少？", False, "none"),
    ("最近销售额是多少？", True, "time"),
    ("卖得最好的商品", True, "metric"),
    ("退款率最高的商品类别", False, "none"),
    ("各城市有效订单数量", False, "none"),
])
def test_model_decision_and_context(monkeypatch, question, ambiguous, kind):
    def model(messages, temperature):
        assert temperature == 0
        assert gate.BUSINESS_CONTEXT in messages[0]["content"]
        assert gate.STATIC_SCHEMA_METADATA in messages[0]["content"]
        return json.dumps(output(ambiguous, kind))
    monkeypatch.setattr(gate, "generate_text", model)
    assert gate.decide(question, reference_date=date(2026, 9, 12)).decision == (
        "clarify" if ambiguous else "proceed")


def test_malformed_stops_without_sql(monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "generate_text", lambda *a, **k: calls.append(1) or "not JSON")
    monkeypatch.setattr(production, "run_question", lambda *a: pytest.fail("SQL must not run"))
    assert production.run_interactive("问题")["status"] == "clarification_unavailable"
    assert len(calls) == 2


def test_format_retry_recovers(monkeypatch):
    responses = iter(["{}", json.dumps(output())])
    monkeypatch.setattr(gate, "generate_text", lambda *a, **k: next(responses))
    assert gate.decide("问题", reference_date=date.today()).decision == "proceed"


def test_api_interaction_and_round_limit(monkeypatch):
    decisions = iter([output(True), output(), output(True), output(True)])
    monkeypatch.setattr(gate, "generate_text", lambda *a, **k: json.dumps(next(decisions)))
    executed = []
    def engine(question):
        executed.append(question)
        return dict(status="success", result=[{"n": 1}], trace=[])
    monkeypatch.setattr(production, "run_question", engine)
    client = TestClient(app)
    first = production.run_interactive("最近销售额")
    assert first["status"] == "needs_clarification" and not executed
    request = dict(question="最近销售额", clarification_answer="最近30天",
                   clarification_context=first["clarification_context"])
    second = client.post("/api/query", json=request).json()
    assert second["status"] == "success"
    assert "最近30天" in executed[0] and "最近销售额" in executed[0]
    first = production.run_interactive("最近销售额")
    request["clarification_context"] = first["clarification_context"]
    request["clarification_answer"] = "随便"
    assert client.post("/api/query", json=request).json()["status"] == "needs_rephrase"
    assert len(executed) == 1
    request["clarification_context"]["rounds"] = 2
    assert client.post("/api/query", json=request).status_code == 422


def test_clear_compatible_request(monkeypatch):
    from app.agent import scoped_clarification
    monkeypatch.setattr(scoped_clarification, "direct", lambda *a: dict(status="success", result=[], trace=[]))
    monkeypatch.setattr(gate, "generate_text", lambda *a, **k: json.dumps(output()))
    monkeypatch.setattr(production, "run_question", lambda *a: dict(status="success", result=[], trace=[]))
    assert TestClient(app).post("/api/query", json={"question": "有效订单数"}).json()["status"] == "success"


@pytest.mark.parametrize("payload", [{"question": " "}, {"question": "q", "clarification_answer": "a"}])
def test_bad_request(payload):
    assert TestClient(app).post("/api/query", json=payload).status_code == 422


def test_transport_error_is_sanitized(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private upstream detail")
    monkeypatch.setattr(gate, "generate_text", fail)
    result = production.run_interactive("问题")
    assert result["status"] == "clarification_unavailable"
    assert "private" not in str(result)
