"""Mature static-context NL2SQL baseline for the final v2 comparison."""

from __future__ import annotations

import re
import time
from typing import Any

from app.tools.database import execute_agent_select
from app.tools.guardrail import validate_and_rewrite_sql
from app.tools.qwen import generate_text
from eval.strong_baseline import (
    BUSINESS_CONTEXT,
    MAX_RETRY,
    SQL_TEMPERATURE,
    extract_sql,
    schema_context,
)


ALIAS_RULES = (
    ("客户", "用户"),
    ("产品", "商品"),
    ("成交额", "销售额"),
    ("实收金额", "销售额"),
    ("销售数量", "销量"),
    ("卖出数量", "销量"),
    ("退款额", "退款金额"),
    ("下单量", "订单数"),
)


STATIC_SCHEMA_METADATA = """Static schema metadata:
- users: customer master data. user_id is the customer key; user_name is the display name;
  user_level values are normal/silver/gold/black; city and province are customer location;
  is_vip=1 means VIP; register_date is the registration date.
- products: product master data. product_id is the product key; category and brand are product
  dimensions; list_price is the displayed price; cost_price is product cost; launch_date is the
  listing date; is_active=1 means currently active/on sale. Category values include 家用电器,
  手机数码, 服饰鞋包, 母婴用品, 美妆个护, 运动户外 and 食品生鲜.
- orders: order headers. order_id identifies an order; user_id identifies its customer;
  order_status values include paid/completed/shipped/cancelled/unpaid; payment_method values are
  alipay/wechat/card/cash; gross_amount is pre-discount amount; discount_amount is order discount;
  paid_amount is actual customer payment; order_date is the business date.
- order_items: product lines in orders. order_item_id identifies a line; order_id and product_id
  are foreign keys; quantity is units sold; unit_price is transaction unit price;
  discount_amount is line discount; item_amount is actual paid amount for the line.
- refunds: refund records. refund_id identifies a refund; order_id links its order; product_id and
  order_item_id may identify the refunded product/line; refund_status values are approved/rejected/pending;
  refund_amount is requested/processed refund money; refund_reason is the reason; refund_date is refund time.
"""


FEW_SHOT_EXAMPLES = """General NL2SQL examples:

Question: Count active products in one named category.
SQL: SELECT COUNT(*) AS product_count FROM products WHERE category = ? AND is_active = 1;

Question: Calculate valid-order sales during a recent N-day window from an explicit reference date.
SQL: SELECT ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date >= DATE_SUB(?, INTERVAL ? DAY);

Question: Rank users by valid-order spending and return the requested Top K.
SQL: SELECT u.user_name, ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY u.user_id,u.user_name ORDER BY sales_amount DESC,u.user_id ASC LIMIT ?;

Question: Group approved refund money by refund reason.
SQL: SELECT refund_reason, ROUND(SUM(refund_amount),2) AS refund_amount FROM refunds WHERE refund_status='approved' GROUP BY refund_reason;

Question: Show monthly valid-order sales in chronological order.
SQL: SELECT DATE_FORMAT(order_date,'%Y-%m') AS month, ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') GROUP BY month ORDER BY month;

Question marks are placeholders showing the general pattern. Replace them with literals from the actual question; do not emit parameter placeholders.
"""


SYSTEM_PROMPT = """You generate MySQL 8 SQL for business analytics.
Return only one SQL query without markdown, comments, or explanation.
Only SELECT or WITH ... SELECT is allowed.
Use only columns and foreign keys present in the supplied static schema.
Follow the supplied business and time definitions.
Return exactly the columns requested by the user.
For monetary results use ROUND(..., 2); for rates use ROUND(..., 4).
The examples demonstrate general SQL patterns and do not add filters absent from the question.
"""


def normalize_aliases(question: str) -> str:
    normalized = question
    for alias, canonical in ALIAS_RULES:
        normalized = re.sub(re.escape(alias), canonical, normalized)
    return normalized


def build_messages(question: str, schema: str, sql: str = "", error: str = ""):
    normalized = normalize_aliases(question)
    user = f"""Static database schema:
{schema}

{STATIC_SCHEMA_METADATA}

{BUSINESS_CONTEXT}

{FEW_SHOT_EXAMPLES}

Original question:
{question}

Question with vocabulary aliases normalized:
{normalized}
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
        sql = extract_sql(
            generate_text(build_messages(question, schema, sql, error), temperature=SQL_TEMPERATURE)
        )
        try:
            guard = validate_and_rewrite_sql(sql)
        except Exception as exc:
            guard = None
            error = str(exc)
        if guard is None or not guard.ok:
            if guard is not None:
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
        "normalized_question": normalize_aliases(question),
        "sql": sql,
        "result": result,
        "error": error,
        "retry_count": retry_count,
        "status": status,
        "trace": trace,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
