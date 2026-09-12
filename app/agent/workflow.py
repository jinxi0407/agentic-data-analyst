"""Single-agent LangGraph workflow for Agentic Data Analyst."""

from __future__ import annotations

import re
import time
from functools import wraps
from typing import Any, Callable, Dict

from langgraph.graph import END, StateGraph

from app.agent.prompts import build_final_answer_messages, build_sql_messages
from app.agent.query_plan import build_query_plan, format_query_plan
from app.agent.skill_router import route_skill
from app.agent.state import GraphState
from app.config import settings
from app.schema.metadata import build_schema_text, retrieve_relevant_schema
from app.tools.analysis import analyze_rows
from app.tools.database import execute_agent_select
from app.tools.guardrail import validate_and_rewrite_sql
from app.tools.qwen import generate_text


def _trace_node(name: str):
    def decorator(func: Callable[[GraphState], Dict[str, Any]]):
        @wraps(func)
        def wrapper(state: GraphState) -> Dict[str, Any]:
            started = time.perf_counter()
            update: Dict[str, Any] = {}
            status = "error"
            try:
                update = func(state)
                status = "success"
            except Exception as exc:
                update = {
                    "status": "error",
                    "execution_error": str(exc),
                    "final_answer": f"节点 {name} 执行失败：{exc}",
                }
                status = "error"
            finally:
                latency_ms = int((time.perf_counter() - started) * 1000)
                trace = list(state.get("trace", []))
                trace.append(
                    {
                        "node": name,
                        "status": status,
                        "latency_ms": latency_ms,
                        "retry_count": state.get("retry_count", 0),
                    }
                )
                update["trace"] = trace
            return update

        return wrapper

    return decorator


@_trace_node("skill_router")
def skill_router_node(state: GraphState) -> Dict[str, Any]:
    routed = route_skill(state["question"])
    return {**routed, "step_count": state.get("step_count", 0) + 1}


@_trace_node("schema_retrieval")
def schema_retrieval_node(state: GraphState) -> Dict[str, Any]:
    schema = retrieve_relevant_schema(state["question"])
    return {
        "matched_tables": schema["matched_tables"],
        "matched_columns": schema["matched_columns"],
        "db_schema": schema["db_schema"],
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("query_planning")
def query_planning_node(state: GraphState) -> Dict[str, Any]:
    plan = build_query_plan(state["question"], state.get("skill_name", ""))
    matched_tables = sorted(set(state.get("matched_tables", [])) | set(plan.get("required_tables", [])))
    db_schema = build_schema_text(matched_tables)
    return {
        "query_plan": plan,
        "query_plan_text": format_query_plan(plan),
        "matched_tables": matched_tables,
        "db_schema": db_schema,
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("generate_sql")
def generate_sql_node(state: GraphState) -> Dict[str, Any]:
    text = generate_text(build_sql_messages(state), temperature=0.05)
    return {
        "sql": extract_sql(text),
        "validation_error": "",
        "execution_error": "",
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("sql_guardrail")
def sql_guardrail_node(state: GraphState) -> Dict[str, Any]:
    result = validate_and_rewrite_sql(state.get("sql", ""))
    if not result.ok:
        return {
            "validation_error": result.error,
            "status": "validation_error",
            "step_count": state.get("step_count", 0) + 1,
        }
    return {
        "sql": result.sql,
        "validation_error": "",
        "status": "sql_valid",
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("execute_sql")
def execute_sql_node(state: GraphState) -> Dict[str, Any]:
    rows = execute_agent_select(state["sql"])
    return {
        "query_result": rows,
        "execution_error": "",
        "status": "executed",
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("analyze_result")
def analyze_result_node(state: GraphState) -> Dict[str, Any]:
    analysis = analyze_rows(state.get("skill_name", ""), state.get("query_result", []))
    return {
        "analysis_result": analysis,
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("final_answer")
def final_answer_node(state: GraphState) -> Dict[str, Any]:
    text = generate_text(build_final_answer_messages(state), temperature=0.2)
    start = state.get("start_time") or time.time()
    return {
        "final_answer": text,
        "latency_ms": int((time.time() - start) * 1000),
        "status": "success",
        "step_count": state.get("step_count", 0) + 1,
    }


def route_after_guardrail(state: GraphState) -> str:
    if state.get("validation_error"):
        if state.get("retry_count", 0) < settings.max_retry:
            return "repair_sql"
        return "final_error"
    return "execute_sql"


def route_after_external_node(state: GraphState) -> str:
    if state.get("execution_error") and state.get("status") == "error":
        return "final_error"
    return "continue"


def route_after_execute(state: GraphState) -> str:
    if state.get("execution_error"):
        if state.get("retry_count", 0) < settings.max_retry:
            return "repair_sql"
        return "final_error"
    return "analyze_result"


@_trace_node("repair_sql")
def repair_sql_node(state: GraphState) -> Dict[str, Any]:
    text = generate_text(build_sql_messages(state), temperature=0.05)
    return {
        "sql": extract_sql(text),
        "retry_count": state.get("retry_count", 0) + 1,
        "validation_error": "",
        "execution_error": "",
        "step_count": state.get("step_count", 0) + 1,
    }


@_trace_node("final_error")
def final_error_node(state: GraphState) -> Dict[str, Any]:
    start = state.get("start_time") or time.time()
    error = state.get("validation_error") or state.get("execution_error") or "Unknown error"
    return {
        "final_answer": f"本次查询失败，已达到最大重试次数。最后错误：{error}",
        "latency_ms": int((time.time() - start) * 1000),
        "status": "failed",
    }


def build_graph():
    builder = StateGraph(GraphState)
    builder.add_node("skill_router", skill_router_node)
    builder.add_node("schema_retrieval", schema_retrieval_node)
    builder.add_node("query_planning", query_planning_node)
    builder.add_node("generate_sql", generate_sql_node)
    builder.add_node("sql_guardrail", sql_guardrail_node)
    builder.add_node("execute_sql", execute_sql_node)
    builder.add_node("repair_sql", repair_sql_node)
    builder.add_node("analyze_result", analyze_result_node)
    builder.add_node("final_answer", final_answer_node)
    builder.add_node("final_error", final_error_node)

    builder.set_entry_point("skill_router")
    builder.add_edge("skill_router", "schema_retrieval")
    builder.add_conditional_edges(
        "schema_retrieval",
        route_after_external_node,
        {"continue": "query_planning", "final_error": "final_error"},
    )
    builder.add_conditional_edges(
        "query_planning",
        route_after_external_node,
        {"continue": "generate_sql", "final_error": "final_error"},
    )
    builder.add_conditional_edges(
        "generate_sql",
        route_after_external_node,
        {"continue": "sql_guardrail", "final_error": "final_error"},
    )
    builder.add_conditional_edges("sql_guardrail", route_after_guardrail)
    builder.add_conditional_edges("execute_sql", route_after_execute)
    builder.add_edge("repair_sql", "sql_guardrail")
    builder.add_edge("analyze_result", "final_answer")
    builder.add_edge("final_answer", END)
    builder.add_edge("final_error", END)
    return builder.compile()


def run_question(question: str) -> GraphState:
    initial_state: GraphState = {
        "question": question,
        "skill_name": "",
        "skill_content": "",
        "matched_tables": [],
        "matched_columns": [],
        "db_schema": "",
        "query_plan": {},
        "query_plan_text": "",
        "sql": "",
        "validation_error": "",
        "execution_error": "",
        "query_result": [],
        "retry_count": 0,
        "step_count": 0,
        "analysis_result": {},
        "final_answer": "",
        "trace": [],
        "start_time": time.time(),
        "latency_ms": 0,
        "status": "pending",
    }
    return build_graph().invoke(initial_state)


def extract_sql(text: str) -> str:
    block = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    match = re.search(r"((?:WITH|SELECT)[\s\S]*)", text, re.IGNORECASE)
    return (match.group(1) if match else text).strip().rstrip(";")
