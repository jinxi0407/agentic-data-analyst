# Agent v1 Evaluation - Strong Baseline

## Scope

Accuracy Hardening Phase 1 only changed business semantics, time semantics, join context, Top-K semantics, lightweight query planning, and paraphrase normalization. It did not add MCP, Multi-Agent, A2A, new models, new databases, semantic verifier, result verifier, or a second self-correction system.

## Fixed Benchmark

- Main Set: 240
- Paraphrase Set: 40
- Repair Challenge: 20
- Safety Set: 30
- Reference date: 2026-09-12
- Database: existing seeded `agentic_data_analyst`
- Chat model: existing Qwen / DashScope config
- Embedding model: existing `text-embedding-v4`
- Ground truth: unchanged `expected_result` from `eval/final_cases.json`

## Overall Metrics

| Metric | Direct Baseline | Agent v0 | Agent v1 |
|---|---:|---:|---:|
| Execution Accuracy | 0.1571 | 0.1714 | 0.5000 |
| SQL Execution Rate | 0.9750 | 1.0000 | 0.9786 |
| Average Retry | 0.0000 | 0.0107 | 0.0429 |
| Average Latency ms | 3742.28 | 8277.46 | 7465.85 |

Accuracy improvement from Agent v0 to Agent v1: +0.3286 (+32.86 percentage points).

## Difficulty Accuracy

| Difficulty | v0 Agent | Agent v1 | Change |
|---|---:|---:|---:|
| easy | 0.5000 | 0.8500 | +0.3500 |
| medium | 0.0238 | 0.4365 | +0.4127 |
| hard | 0.1596 | 0.3617 | +0.2021 |

## Category Accuracy

| Category | v0 Agent | Agent v1 | Change |
|---|---:|---:|---:|
| simple_filtering | 1.0000 | 1.0000 | +0.0000 |
| aggregation | 0.4000 | 1.0000 | +0.6000 |
| top_k_ranking | 0.0000 | 0.3600 | +0.3600 |
| time_range | 0.0000 | 0.8000 | +0.8000 |
| multi_table_join | 0.0000 | 0.6000 | +0.6000 |
| complex_conditions | 0.0000 | 0.2000 | +0.2000 |
| trend_mom_yoy | 0.2000 | 0.4000 | +0.2000 |
| refund_analysis | 0.2000 | 0.6000 | +0.4000 |
| customer_product | 0.4000 | 0.2000 | -0.2000 |
| paraphrase | 0.0000 | 0.1500 | +0.1500 |

## Retrieval, Repair, Safety

- Schema Retrieval Recall@K: 1.0000
- Repair Success Rate: 0.8000
- Average Repair Retry: 1.0000
- Guardrail Block Rate: 1.0000
- Guardrail False Positive Rate: 0.0000
- Guardrail False Negative Rate: 0.0000

## What Changed

- Added a canonical Business Metric Dictionary for sales, quantity, paid amount, average order amount, refund amount, refund rate, valid orders, and paid users.
- Added fixed time semantics for relative windows, complete natural months, quarter/year boundaries, MoM, and YoY.
- Added explicit foreign-key join context for users, orders, order_items, products, and refunds.
- Added deterministic lightweight Query Plan before SQL generation.
- Added paraphrase normalization for refund, sales, quantity, high-value customer, and recent-quarter phrasing.
- Passed the same context into SQL repair prompts through the existing prompt builder.

## Bad Cases

Failure type counts for Agent v1:

```json
{
  "result mismatch / metric drift": 78,
  "row count mismatch": 62
}
```

Worst three categories:

```json
[
  [
    "paraphrase",
    0.15
  ],
  [
    "complex_conditions",
    0.2
  ],
  [
    "customer_product",
    0.2
  ]
]
```

Sample failures:

```json
[
  {
    "id": "main_047",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，购买数量最多的10个商品是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "sales_analysis",
    "expected_tables": [
      "order_items",
      "products"
    ],
    "retrieved_tables": [
      "order_items",
      "orders",
      "products",
      "users"
    ],
    "schema_recall": 1.0,
    "generated_sql": "SELECT p.product_name FROM order_items AS oi JOIN products AS p ON oi.product_id = p.product_id JOIN orders AS o ON oi.order_id = o.order_id WHERE o.order_status IN ('paid', 'completed', 'shipped') GROUP BY p.product_id, p.product_name ORDER BY SUM(oi.quantity) DESC LIMIT 10",
    "execution_status": "success",
    "result_correct": false,
    "retry_count": 0,
    "latency_ms": 7061,
    "error": "",
    "failure_reason": "missing_expected_row expected=('北辰美妆个护入门款商品018', 735.0)",
    "failure_type": "result mismatch / metric drift"
  },
  {
    "id": "main_048",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，销售额最高的5个品牌是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "sales_analysis",
    "expected_tables": [
      "products",
      "order_items"
    ],
    "retrieved_tables": [
      "order_items",
      "orders",
      "products",
      "users"
    ],
    "schema_recall": 1.0,
    "generated_sql": "SELECT p.brand, ROUND(SUM(oi.item_amount), 2) AS sales_amount FROM order_items AS oi JOIN orders AS o ON oi.order_id = o.order_id JOIN products AS p ON oi.product_id = p.product_id WHERE o.order_status IN ('paid', 'completed', 'shipped') GROUP BY p.brand ORDER BY sales_amount DESC LIMIT 5",
    "execution_status": "success",
    "result_correct": false,
    "retry_count": 0,
    "latency_ms": 6601,
    "error": "",
    "failure_reason": "missing_expected_row expected=('优选', 5710962.51)",
    "failure_type": "result mismatch / metric drift"
  },
  {
    "id": "main_049",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，退款金额最高的10笔订单是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "refund_analysis",
    "expected_tables": [
      "refunds",
      "orders"
    ],
    "retrieved_tables": [
      "order_items",
      "orders",
      "products",
      "refunds",
      "users"
    ],
    "schema_recall": 1.0,
    "generated_sql": "SELECT r.refund_id, r.refund_no, r.order_id, r.refund_amount, r.refund_reason, r.refund_status, r.refund_datetime FROM refunds AS r WHERE r.refund_status = 'approved' ORDER BY r.refund_amount DESC LIMIT 10",
    "execution_status": "success",
    "result_correct": false,
    "retry_count": 0,
    "latency_ms": 11122,
    "error": "",
    "failure_reason": "missing_expected_row expected=('ADA20250713005641', 15730.55)",
    "failure_type": "result mismatch / metric drift"
  },
  {
    "id": "main_052",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，购买数量最多的10个商品是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "sales_analysis",
    "expected_tables": [
      "order_items",
      "products"
    ],
    "retrieved_tables": [
      "order_items",
      "orders",
      "products",
      "users"
    ],
    "schema_recall": 1.0,
    "generated_sql": "SELECT p.product_name FROM order_items AS oi JOIN products AS p ON oi.product_id = p.product_id JOIN orders AS o ON oi.order_id = o.order_id WHERE o.order_status IN ('paid', 'completed', 'shipped') GROUP BY p.product_id, p.product_name ORDER BY SUM(oi.quantity) DESC LIMIT 10",
    "execution_status": "success",
    "result_correct": false,
    "retry_count": 0,
    "latency_ms": 6334,
    "error": "",
    "failure_reason": "missing_expected_row expected=('北辰美妆个护入门款商品018', 735.0)",
    "failure_type": "result mismatch / metric drift"
  },
  {
    "id": "main_053",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，销售额最高的5个品牌是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "sales_analysis",
    "expected_tables": [
      "products",
      "order_items"
    ],
    "retrieved_tables": [
      "order_items",
      "orders",
      "products",
      "users"
    ],
    "schema_recall": 1.0,
    "generated_sql": "SELECT p.brand, ROUND(SUM(oi.item_amount), 2) AS sales_amount FROM order_items AS oi JOIN orders AS o ON oi.order_id = o.order_id JOIN products AS p ON oi.product_id = p.product_id WHERE o.order_status IN ('paid', 'completed', 'shipped') GROUP BY p.brand ORDER BY sales_amount DESC LIMIT 5",
    "execution_status": "success",
    "result_correct": false,
    "retry_count": 0,
    "latency_ms": 6485,
    "error": "",
    "failure_reason": "missing_expected_row expected=('优选', 5710962.51)",
    "failure_type": "result mismatch / metric drift"
  },
  {
    "id": "main_054",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，退款金额最高的10笔订单是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "refund_analysis",
    "expected_tables": [
      "refunds",
      "orders"
    ],
    "retrieved_tables": [
      "order_items",
      "orders",
      "products",
      "refunds",
      "users"
    ],
    "schema_recall": 1.0,
    "generated_sql": "SELECT r.refund_id, r.order_id, r.refund_no, r.refund_amount, r.refund_reason, r.refund_status, r.refund_date FROM refunds AS r WHERE r.refund_status = 'approved' ORDER BY r.refund_amount DESC LIMIT 10",
    "execution_status": "success",
    "result_correct": false,
    "retry_count": 0,
    "latency_ms": 7540,
    "error": "",
    "failure_reason": "missing_expected_row expected=('ADA20250713005641', 15730.55)",
    "failure_type": "result mismatch / metric drift"
  },
  {
    "id": "main_057",
    "pipeline": "agent",
    "question": "以 2026-09-12 为今天，购买数量最多的10个商品是什么？",
    "category": "top_k_ranking",
    "difficulty": "easy",
    "selected_skill": "sales_analysis",
    "expected_tables": [
      "order_items",
      "products"
    ],
    "retrieved_table
```

## Known Limitations

- Complex multi-step business questions still need stronger semantic verification, which is intentionally left for Agent v2.
- Paraphrase accuracy improved but remains weak for vague phrases that combine sales and refund concepts.
- Some Top-K failures are still metric-definition drift, especially when the question can mean sales amount, quantity, or refund severity.
- The current planner is deterministic and lightweight; it helps prompt grounding but does not validate generated SQL results.
- Execution rate is slightly below v0 because stricter prompt context sometimes produces SQL that still needs future syntax hardening.

## Artifacts

- `eval/agent_v1_report.json`
- `eval/agent_v1_per_case_results.json`
- `eval/agent_v1_bad_cases.json`
- `docs/AGENT_V1_EVALUATION.md`
