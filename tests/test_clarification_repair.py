import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent import scoped_clarification as gate
from app.agent import diagnostics as diag
from app.agent import entity_context as entities
from app.main import app


@pytest.fixture
def isolated(monkeypatch):
    sent = []
    monkeypatch.setattr(gate, "schema_context", lambda: "users(user_id, city)")
    monkeypatch.setattr(gate, "entity_context", lambda: "南京 -> 南京市; 北京 -> 北京市; no region substitution")
    def execute(q):
        sent.append(q)
        return {"status": "success", "sql": "SELECT 1", "result": [{"n": 1}], "trace": []}
    monkeypatch.setattr(gate, "run_question", execute)
    return sent


def initial(slot="entity"):
    return {"decision": "clarify", "ambiguity_type": slot, "critical_missing_slots": [slot],
            "alternatives": ["南京市", "北京市"], "clarification_question": "请问具体是哪个城市？"}


@pytest.mark.parametrize("answer", ["南京市", "北京市", "南京"])
def test_followup_schema_and_lossless_merge(monkeypatch, isolated, answer):
    values = iter([initial(), {"decision": "proceed", "missing_slots": [],
                              "resolved_slots": [{"slot": "entity", "quote": answer}]}])
    calls = []
    def generate(messages, **kwargs):
        calls.append(messages)
        assert kwargs["response_format"] == {"type": "json_object"}
        return json.dumps(next(values), ensure_ascii=False)
    monkeypatch.setattr(gate, "generate_text", generate)
    question = "以2026年9月12日为今天，某个城市上个月有效订单销售额最高的5位客户，限VIP。"
    client = TestClient(app)
    first = client.post("/api/scoped-query", json={"question": question, "mode": "clarify"}).json()
    assert not isolated
    final = client.post("/api/scoped-query", json={"question": question, "mode": "clarify",
        "clarification_context": first["clarification_context"], "clarification_answer": answer}).json()
    assert final["status"] == "success" and len(isolated) == 1
    assert question in isolated[0] and answer in isolated[0]
    schema = json.loads(calls[1][0]["content"].split("Response JSON Schema:\n")[1])
    assert set(schema["properties"]) == {"decision", "resolved_slots", "missing_slots"}
    assert final["interaction"]["resolved_slots"] == [{"slot": "entity", "quote": answer}]
    assert final["interaction"]["known_constraints"] == []


def test_original_captured_failure_replays_without_sql(monkeypatch, isolated):
    # The first response retained the question; its retry misattributed answer evidence.
    first = dict(decision="proceed", ambiguity_type="none", known_constraints=[{"slot":"entity","quote":"南京市"}],
                 missing_slots=[], clarification_question="请问具体是哪个城市？", options=[],
                 resolved_slots=[{"slot":"entity","quote":"南京市"}])
    with pytest.raises(ValidationError, match="Proceed must be complete"):
        gate.Decision.model_validate(first)
    first["clarification_question"] = ""
    context = gate.Context(original_question="帮我统计某个城市的用户数量。", known_constraints=[],
                           missing_slots=["entity"], clarification_question="请问具体是哪个城市？", reference_date=date.today())
    with pytest.raises(ValueError, match="not grounded"):
        gate.validate_evidence(gate.Decision.model_validate(first), context.original_question, context, "南京市")
    with pytest.raises(ValidationError):
        gate.FollowupDecision.model_validate(first)
    assert not isolated


@pytest.mark.parametrize("output", [
    {"decision":"proceed","missing_slots":["entity"],"resolved_slots":[]},
    {"decision":"clarify","missing_slots":["entity"],"resolved_slots":[]},
    {"decision":"proceed","missing_slots":[],"resolved_slots":[{"slot":"metric","quote":"销量"}]},
    {"decision":"proceed","missing_slots":[],"resolved_slots":[{"slot":"entity","quote":"北京市"}]},
])
def test_invalid_followup_never_executes(monkeypatch, isolated, output):
    monkeypatch.setattr(gate,"generate_text",lambda *a,**k:json.dumps(output))
    context = gate.Context(original_question="某个城市用户数",known_constraints=[],missing_slots=["entity"],
                           clarification_question="哪座城市？",reference_date=date.today())
    p = gate.run_interactive(context.original_question,"南京市",context)
    assert p["status"] == "invalid_output" and not isolated and p["validation_errors"]


def test_irrelevant_answer_and_new_question_do_not_inherit_city(monkeypatch, isolated):
    values = iter([{"decision":"needs_rephrase","missing_slots":["entity"],"resolved_slots":[]},
                   {"decision":"proceed","critical_missing_slots":[],"alternatives":[],"ambiguity_type":"none","clarification_question":""}])
    monkeypatch.setattr(gate,"generate_text",lambda *a,**k:json.dumps(next(values)))
    context = gate.Context(original_question="城市用户数",known_constraints=[],missing_slots=["entity"],
                           clarification_question="哪座城市？",reference_date=date.today())
    assert gate.run_interactive("城市用户数","天气真好",context)["status"] == "needs_rephrase"
    assert not isolated
    assert gate.run_interactive("全部用户数")["status"] == "success"
    assert "天气真好" not in isolated[0] and "哪座城市" not in isolated[0]


def test_verified_city_alias_uniqueness(monkeypatch):
    entities.city_metadata.cache_clear()
    monkeypatch.setattr(entities,"fetch_all",lambda *a:[{"city":"南京市","province":"江苏"},
        {"city":"北京市","province":"北京"},{"city":"同名市","province":"甲"},{"city":"同名","province":"乙"}])
    try:
        rows = entities.city_metadata()
        assert rows[0]["verified_aliases"] == ["南京"] and rows[1]["verified_aliases"] == ["北京"]
        assert rows[2]["verified_aliases"] == rows[3]["verified_aliases"] == []
    finally:
        entities.city_metadata.cache_clear()


def test_request_id_and_log_redaction(monkeypatch, isolated):
    monkeypatch.setattr(gate,"generate_text",lambda *a,**k:pytest.fail("OFF called Gate"))
    rid="01985f0a-81e1-4000-8000-000000000001"
    p=TestClient(app).post("/api/scoped-query",json={"question":"用户数","mode":"direct"},headers={"X-Request-ID":rid})
    assert p.headers["X-Request-ID"] == p.json()["request_id"] == rid
    assert p.json()["mode"] == "direct"
    token=diag.request_id.set(rid)
    try:
        diag.model_output(json.dumps({"decision":"proceed","reasoning_content":"HIDDEN_TEST_REASONING","api_key":"SECRET_TEST_VALUE"}))
    finally:
        diag.request_id.reset(token)
    data=(diag.LOG_DIR/(rid+".jsonl")).read_text()
    assert "query_received" in data and "HIDDEN_TEST_REASONING" not in data and "SECRET_TEST_VALUE" not in data
