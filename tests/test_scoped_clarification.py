import json
from datetime import date

import pytest

from app.agent import scoped_clarification as gate
from app.agent import entity_context as entities


def decision(kind="proceed", slots=None, resolved=None):
    return dict(decision=kind, ambiguity_type="none" if kind == "proceed" else "time",
                known_constraints=[], missing_slots=slots or [],
                clarification_question="请给出时间范围" if kind == "clarify" else "",
                options=[], resolved_slots=resolved or [])


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch):
    monkeypatch.setattr(gate, "schema_context", lambda: "schema")
    monkeypatch.setattr(gate, "entity_context", lambda: "verified entities")
    monkeypatch.setattr(gate, "run_question", lambda q: dict(status="success", result=[], trace=[], submitted=q))
    monkeypatch.setattr(gate, "generate_text", lambda *a, **kw: pytest.fail("Unmocked API call"))


@pytest.mark.parametrize("q", ["上个月销量", "各城市有效订单数", "深圳客户人数"])
def test_clear_keeps_original(monkeypatch, q):
    monkeypatch.setattr(gate, "generate_text", lambda *a, **kw: json.dumps(decision()))
    result = gate.run_interactive(q, reference_date=date(2026, 9, 12))
    assert result["status"] == "success" and q in result["submitted"]


def test_one_round_merge_only_missing(monkeypatch):
    out = iter([decision("clarify", ["time"]), decision(resolved=[{"slot": "time", "quote": "最近30天"}])])
    monkeypatch.setattr(gate, "generate_text", lambda *a, **kw: json.dumps(next(out)))
    q = "最近商品销售额前5名"
    first = gate.run_interactive(q)
    context = gate.Context.model_validate(first["clarification_context"])
    final = gate.run_interactive(q, "最近30天，顺便改成前10名", context)
    assert q in final["submitted"] and "最近30天" in final["submitted"]
    assert "前10名" not in final["submitted"]


def test_irrelevant_answer_stops(monkeypatch):
    out = iter([decision("clarify", ["time"]), decision("needs_rephrase", ["time"])])
    monkeypatch.setattr(gate, "generate_text", lambda *a, **kw: json.dumps(next(out)))
    first = gate.run_interactive("近期销售额")
    assert gate.run_interactive("近期销售额", "随便", gate.Context.model_validate(first["clarification_context"]))["status"] == "needs_rephrase"


def test_format_has_one_retry_and_no_execution(monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "generate_text", lambda *a, **kw: calls.append(kw) or "{}")
    assert gate.run_interactive("q")["status"] == "invalid_output"
    assert len(calls) == 2 and calls[0]["response_format"]["json_schema"]["strict"]


def test_fabricated_or_unasked_evidence_rejected():
    d = gate.Decision.model_validate(decision(resolved=[{"slot": "metric", "quote": "销量"}]))
    context = gate.Context(original_question="销售额", known_constraints=[], missing_slots=["time"],
                           clarification_question="时间？", reference_date=date.today())
    with pytest.raises(ValueError):
        gate.validate_evidence(d, "销售额", context, "销量")


def test_city_aliases_and_missing_city(monkeypatch):
    entities.city_metadata.cache_clear()
    monkeypatch.setattr(entities, "fetch_all", lambda sql: [{"city": "上海市", "province": "上海"}])
    assert entities.city_metadata()[0]["verified_aliases"] == ["上海"]
    assert "深圳" not in str(entities.city_metadata())
    entities.city_metadata.cache_clear()


def test_scoped_api_roundtrip_and_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    responses = iter([decision("clarify", ["time"]), decision(resolved=[{"slot":"time","quote":"上个月"}])])
    monkeypatch.setattr(gate,"generate_text",lambda *a,**kw:json.dumps(next(responses)))
    client=TestClient(app)
    direct=client.post("/api/scoped-query",json={"question":"销量"})
    assert direct.json()["status"]=="success"
    first=client.post("/api/scoped-query",json={"question":"近期销量","mode":"clarify"}).json()
    request={"question":"近期销量","mode":"clarify","clarification_answer":"上个月",
             "clarification_context":first["clarification_context"]}
    assert client.post("/api/scoped-query",json=request).json()["status"]=="success"
    request["mode"]="direct"
    assert client.post("/api/scoped-query",json=request).status_code==422
