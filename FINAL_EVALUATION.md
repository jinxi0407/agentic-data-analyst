# Final Evaluation - v1.0 Freeze Candidate

## Dataset规模

```json
{
  "users": 3000,
  "products": 800,
  "orders": 12000,
  "order_items": 27523,
  "refunds": 3080
}
```

## Benchmark设计

- Main Set: 240
- Real-user Paraphrase Set: 40
- Repair Challenge: 20
- Safety Set: 30
- Reference Date: 2026-09-12
- Ground Truth: fixed reference SQL executed on the seeded MySQL database.

## Baseline定义

Direct NL2SQL Baseline = User Question + Full Database Schema + same Qwen model. It does not use Skill Router, Schema Retrieval, Retry, Repair, or Agent Harness.

## Agent定义

Current Agent = Skill Router + SKILL.md + Schema Retrieval + Qwen NL2SQL + SQL Guardrail + MySQL Execution + Repair + Pandas Analysis.

## Baseline vs Agent最终指标

| Metric | Baseline | Agent |
|---|---:|---:|
| Execution Accuracy | 0.1571 | 0.5000 |
| SQL Execution Rate | 0.9750 | 0.9786 |
| Average Retry | 0.00 | 0.04 |
| Average Latency ms | 3742.28 | 7465.85 |

## Difficulty指标

```json
{
  "easy": 0.85,
  "medium": 0.4365079365079365,
  "hard": 0.3617021276595745
}
```

## Category指标

```json
{
  "simple_filtering": 1.0,
  "aggregation": 1.0,
  "top_k_ranking": 0.36,
  "time_range": 0.8,
  "multi_table_join": 0.6,
  "complex_conditions": 0.2,
  "trend_mom_yoy": 0.4,
  "refund_analysis": 0.6,
  "customer_product": 0.2,
  "paraphrase": 0.15
}
```

## Schema Retrieval Recall

Schema Retrieval Recall@K: 1.0000

## Repair结果

```json
{
  "total": 20,
  "repair_success_count": 16,
  "repair_success_rate": 0.8,
  "average_repair_retry": 1,
  "average_repair_latency_ms": 8534.15
}
```

## Guardrail结果

```json
{
  "total": 30,
  "guardrail_block_rate": 1.0,
  "false_positive_rate": 0.0,
  "false_negative_rate": 0.0
}
```

## Bad Case Analysis

```json
{
  "failure_count": 376,
  "failure_types": {
    "time interpretation error": 181,
    "result mismatch": 152,
    "wrong column": 7,
    "business semantics misunderstanding": 6,
    "join error": 30
  },
  "examples": [
    {
      "id": "main_006",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，手机数码品类在售商品数量是多少？",
      "category": "simple_filtering",
      "difficulty": "easy",
      "expected_tables": [
        "products"
      ],
      "generated_sql": "SELECT COUNT(*) FROM products WHERE category = '手机' AND launch_date <= '2026-09-12' LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1132,
      "error": "",
      "failure_reason": "missing_expected_row expected=(113.0,)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_020",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，食品生鲜品类在售商品数量是多少？",
      "category": "simple_filtering",
      "difficulty": "easy",
      "expected_tables": [
        "products"
      ],
      "generated_sql": "SELECT COUNT(*) FROM products WHERE category = '食品' AND launch_date <= '2026-09-12' LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1134,
      "error": "",
      "failure_reason": "missing_expected_row expected=(109.0,)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_022",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，不同支付方式的销售额分布如何？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "orders"
      ],
      "generated_sql": "SELECT payment_method, SUM(paid_amount) AS total_sales FROM orders WHERE order_date <= '2026-09-12' AND order_status IN ('paid', 'completed') GROUP BY payment_method ORDER BY total_sales DESC LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1645,
      "error": "",
      "failure_reason": "missing_expected_row expected=('wechat', 7265271.24)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_024",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，各品类销售额分别是多少？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "products",
        "order_items"
      ],
      "generated_sql": "SELECT p.category, SUM(oi.item_amount) AS category_sales FROM orders AS o JOIN order_items AS oi ON o.order_id = oi.order_id JOIN products AS p ON oi.product_id = p.product_id WHERE o.order_date <= '2026-09-12' AND o.order_status IN ('paid', 'completed') GROUP BY p.category LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 2337,
      "error": "",
      "failure_reason": "missing_expected_row expected=('家用电器', 13086179.99)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_025",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，取消订单占比是多少？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "orders"
      ],
      "generated_sql": "SELECT COUNT(CASE WHEN order_status = 'cancelled' THEN 1 END) * 100.0 / COUNT(*) AS cancel_rate FROM orders WHERE order_date <= '2026-09-12' LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1620,
      "error": "",
      "failure_reason": "missing_expected_row expected=(0.0606,)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_027",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，不同支付方式的销售额分布如何？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "orders"
      ],
      "generated_sql": "SELECT payment_method, SUM(paid_amount) AS total_sales FROM orders WHERE order_date <= '2026-09-12' AND order_status IN ('paid', 'completed') GROUP BY payment_method ORDER BY total_sales DESC LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1820,
      "error": "",
      "failure_reason": "missing_expected_row expected=('wechat', 7265271.24)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_029",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，各品类销售额分别是多少？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "products",
        "order_items"
      ],
      "generated_sql": "SELECT p.category, SUM(oi.item_amount) AS category_sales FROM orders AS o JOIN order_items AS oi ON o.order_id = oi.order_id JOIN products AS p ON oi.product_id = p.product_id WHERE o.order_date <= '2026-09-12' AND o.order_status IN ('paid', 'completed') GROUP BY p.category LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 2324,
      "error": "",
      "failure_reason": "missing_expected_row expected=('家用电器', 13086179.99)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_030",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，取消订单占比是多少？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "orders"
      ],
      "generated_sql": "SELECT COUNT(CASE WHEN order_status = 'cancelled' THEN 1 END) * 100.0 / COUNT(*) AS cancel_rate FROM orders WHERE order_date <= '2026-09-12' LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1556,
      "error": "",
      "failure_reason": "missing_expected_row expected=(0.0606,)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_031",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，各订单状态的订单数分别是多少？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "orders"
      ],
      "generated_sql": "SELECT order_status, COUNT(*) AS order_count FROM orders WHERE order_date <= '2026-09-12' GROUP BY order_status LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1212,
      "error": "",
      "failure_reason": "missing_expected_row expected=('completed', 7652.0)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_032",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，不同支付方式的销售额分布如何？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "orders"
      ],
      "generated_sql": "SELECT payment_method, SUM(paid_amount) AS total_sales FROM orders WHERE order_date <= '2026-09-12' AND order_status IN ('paid', 'completed') GROUP BY payment_method ORDER BY total_sales DESC LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 1821,
      "error": "",
      "failure_reason": "missing_expected_row expected=('wechat', 7265271.24)",
      "failure_type": "time interpretation error"
    },
    {
      "id": "main_034",
      "pipeline": "baseline",
      "question": "以 2026-09-12 为今天，各品类销售额分别是多少？",
      "category": "aggregation",
      "difficulty": "easy",
      "expected_tables": [
        "products",
        "order_items"
      ],
      "generated_sql": "SELECT p.category, SUM(oi.item_amount) AS category_sales FROM orders AS o JOIN order_items AS oi ON o.order_id = oi.order_id JOIN products AS p ON oi.product_id = p.product_id WHERE o.order_date <= '2026-09-12' AND o.order_status IN ('paid', 'completed') GROUP BY p.category LIMIT 200",
      "execution_status": "success",
      "result_correct": false,
      "retry_count": 0,
      "latency_ms": 2383,
      "error": "",
      "failure_re
```

## Known Limitations

- Evaluation compares query result tables, not natural-language final answer wording.
- Repair Challenge is fault-injection evaluation and should not be mixed into ordinary benchmark accuracy.
- Some semantically equivalent SQL can still fail strict result comparison if it returns a different projection shape.

## Freeze Status

This project is a v1.0 Freeze Candidate. No new Agent features should be added unless a core demo bug is found.
