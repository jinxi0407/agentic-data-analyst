"""QueryMate UI; the API's backward-compatible default remains direct mode."""

from __future__ import annotations

import os
import json
from pathlib import Path
import sys
from uuid import uuid4

# Streamlit prepends ui/, whose app.py must not shadow the project package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import pandas as pd
import requests
import streamlit as st
from app.agent import diagnostics as diag


API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8002"))
API_URL = f"http://{API_HOST}:{API_PORT}"

st.set_page_config(page_title="QueryMate", layout="wide")
st.title("QueryMate")
st.caption("支持主动澄清的智能问数系统")


def clear_pending():
    for key in ("payload", "clarification_answer", "request_error", "pending_context",
                "pending_request_id", "last_body", "active_request_id"):
        st.session_state.pop(key, None)


@st.cache_data(ttl=10)
def api_online():
    try:
        return requests.get(f"{API_URL}/health", timeout=3).ok
    except requests.RequestException:
        return False


with st.sidebar:
    st.subheader("运行环境")
    st.text("Engine: Production NL2SQL")
    with st.expander("高级设置"):
        clarification_enabled = st.toggle("自动判断是否澄清", value=True,
            key="clarification_enabled", on_change=clear_pending,
            disabled=st.session_state.get("in_flight", False))
    st.text("Model: Qwen Plus")
    st.text("Database: MySQL")
    st.text("Safety: SQLGlot + Read-only")
    if api_online():
        st.success("API 已连接")
    else:
        st.error("API 未连接")


def submit(body):
    if st.session_state.get("in_flight"):
        return
    body.setdefault("mode", "clarify" if clarification_enabled else "direct")
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False)
    if encoded == st.session_state.get("last_body"):
        return
    st.session_state["outgoing"] = {"body": body, "request_id": str(uuid4()),
                                    "parent": st.session_state.get("pending_request_id", "")}
    st.session_state["in_flight"] = True
    st.rerun()


def send_pending():
    job = st.session_state.pop("outgoing")
    body, rid = job["body"], job["request_id"]
    st.session_state["active_request_id"] = rid
    st.session_state.pop("payload", None)
    token = diag.request_id.set(rid)
    try:
        diag.event("ui_submit", mode=body["mode"], question=body["question"],
                   answer=body.get("clarification_answer"), parent_request_id=job["parent"])
        with st.status("正在分析…", expanded=False) as status:
            response = requests.post(f"{API_URL}/api/scoped-query", json=body, timeout=120,
                                     headers={"X-Request-ID": rid, "X-Parent-Request-ID": job["parent"]})
            response.raise_for_status()
            payload = response.json()
            if payload.get("request_id") and payload["request_id"] != rid:
                raise ValueError("Mismatched request ID")
            payload.update(request_id=rid, mode=body["mode"])
            st.session_state.payload = payload
            diag.event("ui_response", status=payload.get("status"))
            if payload.get("status") == "needs_clarification":
                st.session_state["pending_context"] = payload["clarification_context"]
                st.session_state["pending_request_id"] = rid
            elif payload.get("status") == "success":
                st.session_state.pop("pending_context", None)
                st.session_state.pop("pending_request_id", None)
            if payload.get("status") in ("success", "needs_clarification"):
                st.session_state["last_body"] = json.dumps(body, sort_keys=True, ensure_ascii=False)
            status.update(label="请求已完成", state="complete")
        st.session_state.pop("request_error", None)
    except (requests.RequestException, ValueError):
        st.session_state.request_error = "系统请求未完成或响应校验失败；输入已保留，未显示旧结果。"
        diag.event("ui_request_failed")
    finally:
        st.session_state["in_flight"] = False
        diag.request_id.reset(token)
    st.rerun()

examples = [
    "最近30天销售额最高的5个商品是什么？",
    "上个月销售额是多少？",
    "各城市有效订单数量是多少？",
    "最近销售怎么样？",
]

cols = st.columns(2)
for i, example in enumerate(examples):
    if cols[i % 2].button(example, use_container_width=True, disabled=st.session_state.get("in_flight", False)):
        clear_pending()
        st.session_state["question"] = example

with st.form("query"):
    question = st.text_area("业务问题", key="question", height=90, disabled=st.session_state.get("in_flight", False))
    analyze = st.form_submit_button("开始分析", type="primary", disabled=st.session_state.get("in_flight", False))
if analyze:
    if question.strip():
        clear_pending()
        submit({"question": question.strip()})
    else:
        st.warning("请输入业务问题。")

if st.session_state.get("request_error"):
    st.error(st.session_state.request_error)
payload = st.session_state.get("payload", {})
state = payload.get("status")
if payload:
    with st.expander("本次执行信息"):
        st.write({"request_id": payload.get("request_id"), "mode": payload.get("mode"),
                  "Gate": payload.get("gate_decision", {}).get("decision", "未调用" if payload.get("mode") == "direct" else "解析未完成"),
                  "error_code": payload.get("error_code", "")})
        if payload.get("interaction"):
            st.write({"原问题": payload["interaction"]["original_question"],
                      "本次补充字段": payload["interaction"].get("resolved_slots", [])})
if state and state not in ("success", "needs_clarification"):
    messages = {"needs_rephrase": "补充后信息仍不足或有冲突，未执行查询；原问题和输入已保留。",
                "clarification_unavailable": "澄清服务暂时不可用，请稍后重试。",
                "invalid_output": "系统澄清输出未通过校验，未执行查询；不是已确认用户输入有误。",
                "system_error": "系统服务暂时不可用，未完成查询。"}
    st.warning(messages.get(state, "SQL 查询未完成，请查看本次执行信息。"))
pending = st.session_state.get("pending_context")
if pending:
    with st.container(border=True):
        st.subheader("确认一个关键信息")
        st.write(pending["original_question"])
        st.write(pending["clarification_question"] if "clarification_question" in pending else payload.get("clarification_question", ""))
        with st.form("clarification"):
            answer = st.text_input("你的回答", key="clarification_answer", disabled=st.session_state.get("in_flight", False))
            proceed = st.form_submit_button("继续分析", type="primary", disabled=st.session_state.get("in_flight", False))
        if proceed:
            if answer.strip():
                context = pending
                submit({"question": context["original_question"],
                        "mode": "clarify",
                        "clarification_context": context, "clarification_answer": answer.strip()})
            else:
                st.warning("请填写澄清回答。")
if state == "success":
    values = ["查询已执行", f"{payload.get('latency_ms', 0) / 1000:.2f}s", payload.get("retry_count", 0)]
    for col, label, value in zip(st.columns(3), ["状态", "Latency", "执行重试"], values):
        col.metric(label, value)
    result_tab, sql_tab, trace_tab = st.tabs(["查询结果", "SQL", "执行信息"])
    with result_tab:
        frame = pd.DataFrame(payload.get("result", []))
        if frame.empty:
            st.info("查询已执行，没有匹配记录。")
        else:
            st.dataframe(frame, use_container_width=True, hide_index=True)
            numeric = frame.select_dtypes(include="number").columns.tolist()
            labels = [col for col in frame.columns if col not in numeric]
            if 2 <= len(frame) <= 30 and len(frame.columns) == 2 and len(numeric) == len(labels) == 1:
                if st.toggle("显示柱状图", value=False):
                    st.bar_chart(frame, x=labels[0], y=numeric[0])
    with sql_tab:
        st.code(payload.get("sql", ""), language="sql")
    with trace_tab:
        with st.expander("Execution Trace"):
            st.json(payload.get("trace", []))

if st.session_state.get("outgoing"):
    send_pending()
