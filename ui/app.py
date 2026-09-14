"""Streamlit demo UI for Agentic Data Analyst."""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st


API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8002"))
API_URL = f"http://{API_HOST}:{API_PORT}"

st.set_page_config(page_title="Agentic Data Analyst", layout="wide")
st.title("Agentic Data Analyst")
st.caption("企业数据分析 · MySQL")


@st.cache_data(ttl=10)
def api_online():
    try:
        return requests.get(f"{API_URL}/health", timeout=3).ok
    except requests.RequestException:
        return False


with st.sidebar:
    st.subheader("运行环境")
    st.text("Engine: Production NL2SQL")
    clarification_enabled = st.toggle("启用一次主动澄清", value=False,
        help="适合时间、指标或筛选条件尚未明确的问题，可能增加等待时间。")
    st.text("Model: Qwen Plus")
    st.text("Database: MySQL")
    st.text("Safety: SQLGlot + Read-only")
    if api_online():
        st.success("API 已连接")
    else:
        st.error("API 未连接")


def submit(body):
    try:
        with st.status("正在分析…", expanded=False) as status:
            body.setdefault("mode", "clarify" if clarification_enabled else "direct")
            response = requests.post(f"{API_URL}/api/scoped-query", json=body, timeout=120)
            response.raise_for_status()
            st.session_state.payload = response.json()
            status.update(label="分析完成", state="complete")
        st.session_state.pop("request_error", None)
        st.rerun()
    except (requests.RequestException, ValueError):
        st.session_state.request_error = "请求未完成，请检查服务后重试。"

examples = [
    "最近30天销售额最高的5个商品是什么？",
    "上个月销售额是多少？",
    "各城市有效订单数量是多少？",
    "最近销售怎么样？",
]

cols = st.columns(2)
for i, example in enumerate(examples):
    if cols[i % 2].button(example, use_container_width=True):
        st.session_state["question"] = example

with st.form("query"):
    question = st.text_area("业务问题", key="question", height=90)
    analyze = st.form_submit_button("开始分析", type="primary")
if analyze:
    if question.strip():
        st.session_state.pop("payload", None)
        st.session_state.pop("clarification_answer", None)
        submit({"question": question.strip()})
    else:
        st.warning("请输入业务问题。")

if st.session_state.get("request_error"):
    st.error(st.session_state.request_error)
payload = st.session_state.get("payload", {})
state = payload.get("status")
if state == "needs_clarification":
    with st.container(border=True):
        st.subheader("确认一个关键信息")
        st.write(payload["clarification_question"])
        with st.form("clarification"):
            answer = st.text_input("你的回答", key="clarification_answer")
            proceed = st.form_submit_button("继续分析", type="primary")
        if proceed:
            if answer.strip():
                context = payload["clarification_context"]
                submit({"question": context["original_question"],
                        "mode": "clarify",
                        "clarification_context": context, "clarification_answer": answer.strip()})
            else:
                st.warning("请填写澄清回答。")
elif state == "success":
    values = ["成功", f"{payload.get('latency_ms', 0) / 1000:.2f}s", payload.get("retry_count", 0)]
    for col, label, value in zip(st.columns(3), ["状态", "Latency", "执行重试"], values):
        col.metric(label, value)
    result_tab, sql_tab, trace_tab = st.tabs(["查询结果", "SQL", "执行信息"])
    with result_tab:
        frame = pd.DataFrame(payload.get("result", []))
        if frame.empty:
            st.info("查询成功，没有匹配记录。")
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
elif state:
    messages = {"needs_rephrase": "信息仍不足，请在上方重新提交完整、明确的问题。",
                "clarification_unavailable": "澄清服务暂时不可用，请稍后重试。",
                "invalid_output": "澄清输出未通过校验，未执行查询。",
                "system_error": "服务暂时不可用，请稍后重试。"}
    st.warning(messages.get(state, "查询未成功，请检查问题后重试。"))
