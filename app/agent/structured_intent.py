"""Constrained intent parsing and fact-grain guidance for SQL generation."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.business.metrics import business_context_text
from app.tools.qwen import generate_text


Entity = Literal["users", "orders", "order_items", "products", "refunds"]


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["filter", "aggregate", "rank", "trend", "compare"]
    metric: str
    dimensions: list[str]
    filters: list[str]
    time_range: str | None
    direction: Literal["asc", "desc"] | None
    limit: int | None = Field(default=None, ge=1)
    entities: list[Entity]
    target_grain: Entity | Literal["group", "scalar"]
    confidence: float = Field(ge=0, le=1)


def parse_intent(question: str, schema: str) -> dict:
    messages = [
        {"role": "system", "content": (
            "Parse the business question into JSON matching this schema. "
            "Preserve explicit filters, time boundaries, requested output and ranking. "
            "Use the authoritative metric definitions; do not invent restrictions. "
            "Use null for unspecified time/ranking/limit. Return JSON only.\n"
            + json.dumps(Intent.model_json_schema())
        )},
        {"role": "user", "content": question + "\n" + business_context_text() + "\n" + schema},
    ]
    raw = generate_text(messages, temperature=0.05).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return Intent.model_validate_json(raw).model_dump()


GRAIN_GUIDANCE = """
Each users row is one user; products row one product; orders row one order;
order_items row one order line; refunds row one refund record.
Use only FK relationships given in business context and retrieved schema.
Select the output grain before joining. orders.paid_amount belongs to order grain,
order_items.item_amount and quantity to order-line grain, refund_amount to refund grain.
Never sum an order amount after expanding an order into lines or refunds.
For independent sales and refund metrics, aggregate each fact separately to the
requested user/product/group key, then join those aggregates. COALESCE absent refunds
to zero where appropriate. SUM(DISTINCT amount) is not a duplication fix: separate
orders may have equal amounts. For existence-only conditions prefer EXISTS.
Do not introduce pre-aggregation or extra joins when one fact table suffices.
"""


BUSINESS_EXAMPLES = """
General examples (adapt to the actual question; these are not default filters):
1. Customer spending ranking: join users to valid orders, group by user_id and
   user_name, sum orders.paid_amount, order by that sum descending, use requested N.
2. Product refund and sales amounts: aggregate valid order lines by product_id;
   independently aggregate approved refunds by product_id; join aggregates to products.
   Divide refund amount by NULLIF(sales amount,0) only when a refund rate is requested.
3. List customers with at least one matching order: use EXISTS against orders so
   each customer appears once. A request to list orders instead retains order grain.
"""
