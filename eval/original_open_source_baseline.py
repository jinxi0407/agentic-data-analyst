"""Faithful MySQL/Qwen adaptation of upstream woshixiaojunle/NL2SQL-Demo.

The graph structure follows upstream commit eaafb84. Environment-specific
clients and column names are adapted to this project's existing safe config.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, TypedDict

import numpy as np
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.config import settings
from app.tools.database import execute_agent_select, fetch_all
from app.tools.qwen import embed_texts, generate_text


TOP_N = 3
# Upstream used 0.5 with qwen3-vl-embedding. The project's established
# text-embedding-v4 threshold is the environment-compatible equivalent.
SIM_THRESHOLD = settings.schema_similarity_threshold
MAX_RETRY = 2
SQL_TEMPERATURE = 0.05


class OriginalState(TypedDict, total=False):
    question: str
    query_vector: list[float]
    matched_tables: list[dict[str, Any]]
    db_schema: str
    messages: list[dict[str, str]]
    sql: str
    result: list[dict[str, Any]]
    error: str
    retry_count: int
    match_status: str
    exec_status: str


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denominator = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denominator) if denominator else 0.0


def extract_sql(text: str) -> str:
    block = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    bare = re.search(
        r"((?:SELECT|WITH|INSERT|UPDATE|DELETE)[\s\S]+?;)", text, re.IGNORECASE
    )
    if bare:
        return bare.group(1).strip()
    return text.strip()


def embed_query(state: OriginalState) -> dict[str, Any]:
    return {
        "query_vector": embed_texts([state["question"]])[0],
        "match_status": "",
        "exec_status": "pending",
        "error": "",
        "sql": "",
        "result": [],
        "matched_tables": [],
        "db_schema": "",
    }


def retrieve_tables(state: OriginalState) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, table_name, table_comment, embedding_json
        FROM core_table
        WHERE checked = 1
        """
    )
    scored = []
    for row in rows:
        if not row["embedding_json"]:
            continue
        try:
            vector = [float(value) for value in json.loads(row["embedding_json"])]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        scored.append(
            {
                "id": row["id"],
                "table_name": row["table_name"],
                "table_comment": row["table_comment"],
                "similarity": cosine_similarity(state["query_vector"], vector),
            }
        )
    scored.sort(key=lambda item: item["similarity"], reverse=True)
    matched = [item for item in scored[:TOP_N] if item["similarity"] >= SIM_THRESHOLD]
    return {
        "match_status": "ok" if matched else "no_match",
        "matched_tables": matched,
    }


def build_db_schema(state: OriginalState) -> dict[str, str]:
    parts = []
    for table in state["matched_tables"]:
        fields = fetch_all(
            """
            SELECT field_name, field_type, custom_comment
            FROM core_field
            WHERE table_id = %s AND checked = 1
            ORDER BY field_index
            """,
            (table["id"],),
        )
        lines = [
            f"-- {table.get('table_comment') or table['table_name']}",
            f"CREATE TABLE {table['table_name']} (",
        ]
        columns = []
        for field in fields:
            comment = f"  -- {field['custom_comment']}" if field["custom_comment"] else ""
            columns.append(f"  {field['field_name']} {field['field_type']}{comment}")
        lines.extend([",\n".join(columns), ");"])
        parts.append("\n".join(lines))
    return {"db_schema": "\n\n".join(parts)}


def build_prompt(state: OriginalState) -> dict[str, Any]:
    system = """你是一个 MySQL SQL 生成专家。
规则：
1. 只输出 SQL，不要任何解释或注释
2. 使用标准 MySQL 8 语法
3. 字段名和表名使用反引号
4. 当前日期函数使用 CURRENT_DATE
5. 输出的 SQL 必须以分号结尾"""
    human = f"数据库表结构如下：\n\n{state['db_schema']}\n\n用户问题：{state['question']}"
    if state.get("error"):
        human += (
            f"\n\n上次生成的 SQL：\n{state['sql']}"
            f"\n执行报错：{state['error']}"
            "\n请根据错误信息修正 SQL。"
        )
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": human}]}


def generate_sql(state: OriginalState) -> dict[str, str]:
    text = generate_text(state["messages"], temperature=SQL_TEMPERATURE)
    return {"sql": extract_sql(text), "error": ""}


def execute_sql(state: OriginalState) -> dict[str, Any]:
    try:
        return {
            "result": execute_agent_select(state["sql"]),
            "exec_status": "success",
            "error": "",
        }
    except Exception as exc:
        retry = state.get("retry_count", 0) + 1
        return {
            "error": str(exc),
            "exec_status": "error" if retry <= MAX_RETRY else "max_retry",
            "retry_count": retry,
        }


def route_after_retrieve(state: OriginalState) -> str:
    return "build_db_schema" if state["match_status"] == "ok" else END


def route_after_execute(state: OriginalState) -> str:
    return "build_prompt" if state["exec_status"] == "error" else END


def build_graph():
    builder = StateGraph(OriginalState)
    builder.add_node("embed_query", embed_query)
    builder.add_node("retrieve_tables", retrieve_tables)
    builder.add_node("build_db_schema", build_db_schema)
    builder.add_node("build_prompt", build_prompt)
    builder.add_node("generate_sql", generate_sql)
    builder.add_node("execute_sql", execute_sql)
    builder.set_entry_point("embed_query")
    builder.add_edge("embed_query", "retrieve_tables")
    builder.add_conditional_edges("retrieve_tables", route_after_retrieve)
    builder.add_edge("build_db_schema", "build_prompt")
    builder.add_edge("build_prompt", "generate_sql")
    builder.add_edge("generate_sql", "execute_sql")
    builder.add_conditional_edges("execute_sql", route_after_execute)
    return builder.compile(checkpointer=MemorySaver())


GRAPH = build_graph()


def run_question(question: str) -> OriginalState:
    initial: OriginalState = {
        "question": question,
        "query_vector": [],
        "matched_tables": [],
        "db_schema": "",
        "messages": [],
        "sql": "",
        "result": [],
        "error": "",
        "retry_count": 0,
        "match_status": "",
        "exec_status": "pending",
    }
    return GRAPH.invoke(initial, {"configurable": {"thread_id": str(uuid.uuid4())}})
