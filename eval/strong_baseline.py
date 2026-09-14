"""Business-aware single-pass NL2SQL baseline for the final comparison."""

from __future__ import annotations

import re
import time
from typing import Any

from app.config import settings
from app.tools.database import execute_agent_select, fetch_all
from app.tools.guardrail import validate_and_rewrite_sql
from app.tools.qwen import generate_text


SQL_TEMPERATURE = 0.05
MAX_RETRY = 2
TABLES = ("users", "products", "orders", "order_items", "refunds")


BUSINESS_CONTEXT = """Business metric definitions:
- Valid orders: orders.order_status IN ('paid','completed','shipped').
- Sales amount at order/customer/geography grain: SUM(orders.paid_amount) for valid orders.
- Product sales amount: SUM(order_items.item_amount) for lines belonging to valid orders.
- Sales quantity: SUM(order_items.quantity), not order count.
- Refund amount: SUM(refunds.refund_amount) where refund_status='approved'.
- Product refund rate: approved refund amount divided by corresponding product sales amount.
- Paying users: COUNT(DISTINCT orders.user_id) for valid orders.

Basic time semantics:
- An explicit reference date in the question is authoritative.
- Today and yesterday are calendar-day ranges. This month and last month are complete calendar boundaries.
- Last N days/months use DATE_SUB from the explicit reference date.
- Group daily, monthly or yearly trends with the matching date component and order chronologically.
- Order and sales time uses orders.order_date; refund time uses refunds.refund_date.

Foreign keys:
- users.user_id = orders.user_id
- orders.order_id = order_items.order_id
- order_items.product_id = products.product_id
- orders.order_id = refunds.order_id
- order_items.order_item_id = refunds.order_item_id
- products.product_id = refunds.product_id

Basic ranking:
- Top/highest/most uses ORDER BY the requested metric DESC and the requested LIMIT.
- Bottom/lowest/least uses ORDER BY the requested metric ASC and the requested LIMIT.
- Rank by the metric named in the question; do not substitute another numeric column.
"""


SYSTEM_PROMPT = """You generate MySQL 8 SQL for business analytics.
Return only one SQL query without markdown, comments, or explanation.
Only SELECT or WITH ... SELECT is allowed.
Use only columns and relationships present in the supplied schema.
Follow the supplied metric and time definitions.
Return exactly the columns requested by the user.
For monetary results use ROUND(..., 2); for rates use ROUND(..., 4).
"""


def schema_context() -> str:
    placeholders = ",".join(["%s"] * len(TABLES))
    columns = fetch_all(
        f"""
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
               COLUMN_TYPE AS column_type, COLUMN_KEY AS column_key
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name IN ({placeholders})
        ORDER BY FIELD(table_name,{placeholders}), ordinal_position
        """,
        (settings.mysql_database, *TABLES, *TABLES),
    )
    foreign_keys = fetch_all(
        f"""
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
               REFERENCED_TABLE_NAME AS referenced_table_name,
               REFERENCED_COLUMN_NAME AS referenced_column_name
        FROM information_schema.key_column_usage
        WHERE table_schema=%s AND referenced_table_name IS NOT NULL
          AND table_name IN ({placeholders})
        ORDER BY table_name, column_name
        """,
        (settings.mysql_database, *TABLES),
    )
    by_table: dict[str, list[str]] = {table: [] for table in TABLES}
    for column in columns:
        key = " PRIMARY KEY" if column["column_key"] == "PRI" else ""
        by_table[column["table_name"]].append(
            f"  {column['column_name']} {column['column_type']}{key}"
        )
    parts = [f"CREATE TABLE {table} (\n" + ",\n".join(by_table[table]) + "\n);" for table in TABLES]
    relationships = [
        f"{row['table_name']}.{row['column_name']} -> "
        f"{row['referenced_table_name']}.{row['referenced_column_name']}"
        for row in foreign_keys
    ]
    return "\n\n".join(parts) + "\n\nFOREIGN KEYS:\n" + "\n".join(relationships)


def extract_sql(text: str) -> str:
    block = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    bare = re.search(r"((?:WITH|SELECT)[\s\S]*)", text, re.IGNORECASE)
    return (bare.group(1) if bare else text).strip().rstrip(";")


def build_messages(question: str, schema: str, sql: str = "", error: str = ""):
    user = f"""Database schema:
{schema}

Business context:
{BUSINESS_CONTEXT}

Question:
{question}
"""
    if error:
        user += f"""
Previous SQL:
{sql}

Database or syntax error:
{error}

Regenerate the SQL by correcting only this execution or syntax error.
"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def run_question(question: str) -> dict[str, Any]:
    started = time.perf_counter()
    schema = schema_context()
    sql = ""
    error = ""
    retry_count = 0
    result: list[dict[str, Any]] = []
    status = "failed"
    trace = []
    while retry_count <= MAX_RETRY:
        sql = extract_sql(generate_text(build_messages(question, schema, sql, error), temperature=SQL_TEMPERATURE))
        guard = validate_and_rewrite_sql(sql)
        if not guard.ok:
            error = guard.error
            trace.append({"stage": "safety", "status": "error", "error": error})
        else:
            sql = guard.sql
            try:
                result = execute_agent_select(sql)
                status = "success"
                error = ""
                trace.append({"stage": "execute", "status": "success"})
                break
            except Exception as exc:
                error = str(exc)
                trace.append({"stage": "execute", "status": "error", "error": error})
        if retry_count == MAX_RETRY:
            break
        retry_count += 1
    return {
        "question": question,
        "sql": sql,
        "result": result,
        "error": error,
        "retry_count": retry_count,
        "status": status,
        "trace": trace,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
