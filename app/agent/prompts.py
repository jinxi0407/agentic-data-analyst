"""Prompt builders for SQL generation, repair, and final answers."""

from __future__ import annotations

from typing import Any, Dict, List

from app.business.metrics import business_context_text
from app.agent.structured_intent import GRAIN_GUIDANCE, BUSINESS_EXAMPLES


SQL_RULES = """
You generate MySQL 8 SQL for an e-commerce analytics database.
Rules:
1. Output only SQL, no markdown, no explanation.
2. Only SELECT or WITH ... SELECT is allowed.
3. Use the provided relevant schema only.
4. The Business Metric Dictionary is authoritative. Do not invent alternate metric definitions.
5. The Query Plan is a compact interpretation of the question. Follow it unless the original question clearly contradicts it.
6. If the question provides a reference date such as "以 2026-09-12 为今天", use that literal date in DATE_SUB/date filters instead of CURRENT_DATE.
7. Use CURRENT_DATE only when no explicit reference date is provided.
8. Add a LIMIT when returning ranked rows.
9. Use exact category values from the question; do not shorten or translate category names.
10. For grouped numeric business metrics, use ROUND(..., 2); for rates use ROUND(..., 4).
"""


def build_sql_messages(state: Dict[str, Any]) -> List[Dict[str, str]]:
    repair = ""
    if state.get("validation_error") or state.get("execution_error"):
        repair = f"""
Previous SQL:
{state.get('sql', '')}

Validation error:
{state.get('validation_error', '')}

Execution error:
{state.get('execution_error', '')}

Repair the SQL. Retry count: {state.get('retry_count', 0)}.
"""

    user = f"""
Question:
{state['question']}

Selected skill:
{state.get('skill_name', '')}

Skill instructions:
{state.get('skill_content', '')}

Business context:
{business_context_text()}

Lightweight query plan:
{state.get('query_plan_text', '')}

Relevant schema:
{state.get('db_schema', '')}

Structured intent (advisory; the original question remains authoritative):
{state.get('structured_intent', {})}

Grain-aware JOIN planning:
{GRAIN_GUIDANCE}

Business examples:
{BUSINESS_EXAMPLES}

Generate one MySQL query that follows the metric definitions, time semantics, join relationships, ranking rules, and query plan above.
{repair}
"""
    return [
        {"role": "system", "content": SQL_RULES.strip()},
        {"role": "user", "content": user.strip()},
    ]


def build_final_answer_messages(state: Dict[str, Any]) -> List[Dict[str, str]]:
    rows = state.get("query_result", [])[:20]
    user = f"""
User question: {state.get('question', '')}
Skill: {state.get('skill_name', '')}
SQL: {state.get('sql', '')}
Deterministic analysis metrics: {state.get('analysis_result', {})}
Sample rows: {rows}

Write a concise Chinese business analysis. Do not invent numbers outside the SQL result and metrics.
"""
    return [
        {"role": "system", "content": "你是企业智能数据分析 Agent，负责用中文解释 SQL 查询结果。"},
        {"role": "user", "content": user},
    ]
