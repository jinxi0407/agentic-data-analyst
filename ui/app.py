"""Streamlit demo UI for Agentic Data Analyst."""

from __future__ import annotations

import os
import time

import pandas as pd
import requests
import streamlit as st


API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8002"))
API_URL = f"http://{API_HOST}:{API_PORT}"

st.set_page_config(page_title="Agentic Data Analyst", layout="wide")
st.title("Agentic Data Analyst")

examples = [
    "最近30天销售额最高的5个商品是什么？",
    "最近三个月退款率最高的商品有哪些？",
    "过去六个月每月销售额趋势怎么样？",
    "消费金额最高的10位客户是谁？",
]

cols = st.columns(2)
for i, example in enumerate(examples):
    if cols[i % 2].button(example, use_container_width=True):
        st.session_state["question"] = example

question = st.text_area("自然语言问题", value=st.session_state.get("question", examples[0]), height=90)

if st.button("开始分析", type="primary"):
    started = time.time()
    with st.spinner("Agent 正在分析..."):
        response = requests.post(f"{API_URL}/api/query", json={"question": question}, timeout=120)
    response.raise_for_status()
    payload = response.json()

    left, right = st.columns([1, 1])
    left.metric("当前 Skill", payload.get("skill") or "-")
    right.metric("Latency", f"{payload.get('latency_ms', int((time.time() - started) * 1000))} ms")

    st.subheader("命中 Schema / Tables")
    st.write(payload.get("matched_tables", []))
    if payload.get("matched_columns"):
        st.dataframe(pd.DataFrame(payload["matched_columns"]), use_container_width=True)

    st.subheader("生成 SQL")
    st.code(payload.get("sql", ""), language="sql")

    st.subheader("查询结果")
    rows = payload.get("result", [])
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("查询结果为空。")

    st.subheader("业务分析")
    st.write(payload.get("analysis", ""))

    c1, c2 = st.columns(2)
    c1.metric("Retry Count", payload.get("retry_count", 0))
    c2.metric("Status", payload.get("status", "unknown"))

    with st.expander("Agent Trace"):
        st.json(payload.get("trace", []))
