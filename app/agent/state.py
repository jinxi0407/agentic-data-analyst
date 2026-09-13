"""LangGraph state definition for the single-agent workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GraphState(TypedDict, total=False):
    question: str
    skill_name: str
    skill_content: str

    matched_tables: List[str]
    matched_columns: List[Dict[str, Any]]
    db_schema: str
    query_plan: Dict[str, Any]
    query_plan_text: str
    structured_intent: Dict[str, Any]
    intent_status: str

    sql: str
    validation_error: str
    execution_error: str
    query_result: List[Dict[str, Any]]

    retry_count: int
    step_count: int

    analysis_result: Dict[str, Any]
    final_answer: str

    trace: List[Dict[str, Any]]
    start_time: float
    latency_ms: int
    status: str
