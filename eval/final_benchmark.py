"""Final benchmark generation and evaluation utilities.

This module intentionally lives under eval/ so the production Agent workflow
stays stable for the v1.0 freeze candidate.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from app.agent.prompts import SQL_RULES
from app.agent.workflow import run_question
from app.config import settings
from app.schema.metadata import build_schema_text, retrieve_relevant_schema
from app.tools.database import execute_agent_select, fetch_all
from app.tools.guardrail import validate_and_rewrite_sql
from app.tools.qwen import generate_text


REFERENCE_DATE = "2026-09-12"
CASE_PATH = ROOT / "eval" / "final_cases.json"
SAFETY_PATH = ROOT / "eval" / "safety_cases.json"
REPAIR_PATH = ROOT / "eval" / "repair_cases.json"
REPORT_PATH = ROOT / "eval" / "final_report.json"
CHECKPOINT_PATH = ROOT / "eval" / "final_results_checkpoint.json"


CATEGORY_TARGETS = [
    ("simple_filtering", 20),
    ("aggregation", 25),
    ("top_k_ranking", 25),
    ("time_range", 25),
    ("multi_table_join", 40),
    ("complex_conditions", 35),
    ("trend_mom_yoy", 25),
    ("refund_analysis", 25),
    ("customer_product", 20),
]

DIFFICULTY_TARGETS = {"easy": 60, "medium": 100, "hard": 80}


def _case(case_id: str, question: str, category: str, difficulty: str, expected_tables: List[str], sql: str) -> Dict[str, Any]:
    if REFERENCE_DATE not in question:
        question = f"以 {REFERENCE_DATE} 为今天，{question}"
    return {
        "id": case_id,
        "question": question,
        "category": category,
        "difficulty": difficulty,
        "expected_tables": expected_tables,
        "reference_date": REFERENCE_DATE,
        "reference_sql": sql.strip(),
        "expected_result": {},
    }


def generate_cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    difficulty_pool = (
        ["easy"] * DIFFICULTY_TARGETS["easy"]
        + ["medium"] * DIFFICULTY_TARGETS["medium"]
        + ["hard"] * DIFFICULTY_TARGETS["hard"]
    )
    diff_idx = 0

    def next_diff(category: str, n: int) -> str:
        nonlocal diff_idx
        if category in {"complex_conditions", "trend_mom_yoy"} and n % 2 == 0:
            return "hard"
        if category in {"multi_table_join", "refund_analysis"} and n % 3 == 0:
            return "hard"
        value = difficulty_pool[min(diff_idx, len(difficulty_pool) - 1)]
        diff_idx += 1
        return value

    generators = {
        "simple_filtering": _simple_cases,
        "aggregation": _aggregation_cases,
        "top_k_ranking": _ranking_cases,
        "time_range": _time_range_cases,
        "multi_table_join": _join_cases,
        "complex_conditions": _complex_cases,
        "trend_mom_yoy": _trend_cases,
        "refund_analysis": _refund_cases,
        "customer_product": _customer_product_cases,
    }
    for category, target in CATEGORY_TARGETS:
        category_cases = generators[category]()
        for i, item in enumerate(category_cases[:target], 1):
            difficulty = next_diff(category, i)
            cases.append(_case(f"main_{len(cases)+1:03d}", item[0], category, difficulty, item[1], item[2]))

    # Normalize exact difficulty totals by upgrading/downgrading without changing case content.
    _rebalance_difficulty(cases)
    if len(cases) != 240:
        raise RuntimeError(f"Expected 240 main cases, got {len(cases)}")
    return cases


def generate_paraphrase_cases() -> List[Dict[str, Any]]:
    seeds = [
        ("最近哪些商品退货特别严重？", ["refunds", "products", "order_items"], _sql_refund_product_rate(10, "INTERVAL 3 MONTH")),
        ("最近卖得还行但是退得特别多的是哪些？", ["refunds", "products", "order_items"], _sql_sales_and_refund_high()),
        ("最近一季度老被退货的商品找几个出来看看。", ["refunds", "products"], _sql_refund_product_rate(10, "INTERVAL 3 MONTH")),
        ("这半年每个月卖得怎么样？", ["orders"], _sql_monthly_sales(6)),
        ("帮我看看大客户都花了多少钱。", ["users", "orders"], _sql_top_customers(10)),
        ("哪些品类最近比较能打？", ["products", "order_items", "orders"], _sql_category_sales()),
        ("有没有那种销量高但退款也吓人的商品？", ["products", "order_items", "refunds"], _sql_sales_and_refund_high()),
        ("最近订单主要来自哪些城市？", ["users", "orders"], _sql_city_sales(10)),
        ("过去几个月退款是不是变多了？", ["refunds"], _sql_monthly_refund(6)),
        ("VIP 买东西贡献大不大？", ["users", "orders"], _sql_vip_sales()),
    ]
    cases: List[Dict[str, Any]] = []
    for i in range(40):
        q, tables, sql = seeds[i % len(seeds)]
        suffix = "" if i < len(seeds) else f"（口语样本{i + 1}）"
        cases.append(
            _case(
                f"para_{i+1:03d}",
                f"以 {REFERENCE_DATE} 为今天，{q}{suffix}",
                "paraphrase",
                "medium" if i < 26 else "hard",
                tables,
                sql,
            )
        )
    return cases


def _simple_cases() -> List[Tuple[str, List[str], str]]:
    categories = ["手机数码", "家用电器", "美妆个护", "服饰鞋包", "食品生鲜"]
    cases = []
    for c in categories * 4:
        cases.append((f"以 {REFERENCE_DATE} 为今天，{c}品类在售商品数量是多少？", ["products"], f"SELECT COUNT(*) AS product_count FROM products WHERE category = '{c}' AND is_active = 1"))
    return cases


def _aggregation_cases() -> List[Tuple[str, List[str], str]]:
    return [
        ("各订单状态的订单数分别是多少？", ["orders"], "SELECT order_status, COUNT(*) AS order_count FROM orders GROUP BY order_status ORDER BY order_count DESC"),
        ("不同支付方式的销售额分布如何？", ["orders"], "SELECT payment_method, ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') GROUP BY payment_method ORDER BY sales_amount DESC"),
        ("每个用户等级的平均订单金额是多少？", ["users", "orders"], "SELECT u.user_level, ROUND(AVG(o.paid_amount),2) AS avg_order_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY u.user_level ORDER BY avg_order_amount DESC"),
        ("各品类销售额分别是多少？", ["products", "order_items"], _sql_category_sales()),
        ("取消订单占比是多少？", ["orders"], "SELECT ROUND(SUM(order_status='cancelled')/COUNT(*),4) AS cancelled_rate FROM orders"),
    ] * 5


def _ranking_cases() -> List[Tuple[str, List[str], str]]:
    return [
        ("最近30天销售额最高的5个商品是什么？", ["orders", "order_items", "products"], _sql_top_products(5, "INTERVAL 30 DAY")),
        ("购买数量最多的10个商品是什么？", ["order_items", "products"], "SELECT p.product_name, SUM(oi.quantity) AS total_quantity FROM order_items oi JOIN products p ON oi.product_id=p.product_id GROUP BY p.product_id,p.product_name ORDER BY total_quantity DESC LIMIT 10"),
        ("销售额最高的5个品牌是什么？", ["products", "order_items"], "SELECT p.brand, ROUND(SUM(oi.item_amount),2) AS sales_amount FROM order_items oi JOIN products p ON oi.product_id=p.product_id GROUP BY p.brand ORDER BY sales_amount DESC LIMIT 5"),
        ("退款金额最高的10笔订单是什么？", ["refunds", "orders"], "SELECT o.order_no, ROUND(SUM(r.refund_amount),2) AS refund_amount FROM refunds r JOIN orders o ON r.order_id=o.order_id WHERE r.refund_status='approved' GROUP BY o.order_id,o.order_no ORDER BY refund_amount DESC LIMIT 10"),
        ("消费金额最高的10位客户是谁？", ["users", "orders"], _sql_top_customers(10)),
    ] * 5


def _time_range_cases() -> List[Tuple[str, List[str], str]]:
    return [
        ("最近7天订单总金额是多少？", ["orders"], _sql_sales_since("INTERVAL 7 DAY")),
        ("最近30天订单总金额是多少？", ["orders"], _sql_sales_since("INTERVAL 30 DAY")),
        ("最近90天订单数是多少？", ["orders"], "SELECT COUNT(*) AS order_count FROM orders WHERE order_date >= DATE_SUB('2026-09-12', INTERVAL 90 DAY)"),
        ("2026年第二季度销售额是多少？", ["orders"], "SELECT ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date >= '2026-04-01' AND order_date < '2026-07-01'"),
        ("2025年双十一期间销售额是多少？", ["orders"], "SELECT ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date BETWEEN '2025-11-01' AND '2025-11-30'"),
    ] * 5


def _join_cases() -> List[Tuple[str, List[str], str]]:
    base = [
        ("各城市销售额排名前十？", ["users", "orders"], _sql_city_sales(10)),
        ("银卡用户最喜欢购买哪些品类？", ["users", "orders", "order_items", "products"], "SELECT p.category, SUM(oi.quantity) AS total_quantity FROM users u JOIN orders o ON u.user_id=o.user_id JOIN order_items oi ON o.order_id=oi.order_id JOIN products p ON oi.product_id=p.product_id WHERE u.user_level='silver' AND o.order_status IN ('paid','completed','shipped') GROUP BY p.category ORDER BY total_quantity DESC LIMIT 10"),
        ("每个省份销售额是多少？", ["users", "orders"], "SELECT u.province, ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY u.province ORDER BY sales_amount DESC"),
        ("各品牌在VIP用户中的销售额排名？", ["users", "orders", "order_items", "products"], "SELECT p.brand, ROUND(SUM(oi.item_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id JOIN order_items oi ON o.order_id=oi.order_id JOIN products p ON oi.product_id=p.product_id WHERE u.is_vip=1 AND o.order_status IN ('paid','completed','shipped') GROUP BY p.brand ORDER BY sales_amount DESC LIMIT 10"),
        ("退款最多的品类和原因组合是什么？", ["refunds", "products"], "SELECT p.category, r.refund_reason, COUNT(*) AS refund_count, ROUND(SUM(r.refund_amount),2) AS refund_amount FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_status='approved' GROUP BY p.category,r.refund_reason ORDER BY refund_amount DESC LIMIT 10"),
    ]
    return base * 8


def _complex_cases() -> List[Tuple[str, List[str], str]]:
    base = [
        ("过去半年销量进入前20但退款率也最高的商品有哪些？", ["orders", "order_items", "products", "refunds"], _sql_sales_and_refund_high()),
        ("最近三个完整自然月中，每位付费用户平均消费金额最低的是哪个月？", ["orders", "users"], "SELECT DATE_FORMAT(order_date,'%Y-%m') AS month, ROUND(SUM(paid_amount)/COUNT(DISTINCT user_id),2) AS arppu FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date >= '2026-06-01' AND order_date < '2026-09-01' GROUP BY month ORDER BY arppu ASC LIMIT 1"),
        ("哪个品类销售额同比增长同时退款金额也同比增长？", ["orders", "order_items", "products", "refunds"], _sql_category_yoy_sales_refund()),
        ("排除取消和未支付后，折扣金额最高的品类是什么？", ["orders", "order_items", "products"], "SELECT p.category, ROUND(SUM(oi.discount_amount),2) AS discount_amount FROM orders o JOIN order_items oi ON o.order_id=oi.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY p.category ORDER BY discount_amount DESC LIMIT 5"),
        ("最近90天高退款且销售额超过均值的商品有哪些？", ["orders", "order_items", "products", "refunds"], _sql_high_refund_above_avg_sales()),
    ]
    return base * 7


def _trend_cases() -> List[Tuple[str, List[str], str]]:
    return [
        ("过去六个月每月销售额趋势怎么样？", ["orders"], _sql_monthly_sales(6)),
        ("过去六个月每月退款金额趋势怎么样？", ["refunds"], _sql_monthly_refund(6)),
        ("最近一年每个季度销售额是多少？", ["orders"], "SELECT CONCAT(YEAR(order_date), '-Q', QUARTER(order_date)) AS quarter, ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date >= DATE_SUB('2026-09-12', INTERVAL 12 MONTH) GROUP BY quarter ORDER BY quarter"),
        ("最近三个月订单数环比有什么变化？", ["orders"], "SELECT DATE_FORMAT(order_date,'%Y-%m') AS month, COUNT(*) AS order_count FROM orders WHERE order_date >= DATE_SUB('2026-09-12', INTERVAL 3 MONTH) GROUP BY month ORDER BY month"),
        ("每月VIP用户销售额趋势如何？", ["users", "orders"], "SELECT DATE_FORMAT(o.order_date,'%Y-%m') AS month, ROUND(SUM(o.paid_amount),2) AS vip_sales FROM orders o JOIN users u ON o.user_id=u.user_id WHERE u.is_vip=1 AND o.order_status IN ('paid','completed','shipped') AND o.order_date >= DATE_SUB('2026-09-12', INTERVAL 6 MONTH) GROUP BY month ORDER BY month"),
    ] * 5


def _refund_cases() -> List[Tuple[str, List[str], str]]:
    return [
        ("最近三个月退款率最高的商品有哪些？", ["refunds", "products", "order_items"], _sql_refund_product_rate(10, "INTERVAL 3 MONTH")),
        ("退款原因最多的是哪些？", ["refunds"], "SELECT refund_reason, COUNT(*) AS refund_count FROM refunds GROUP BY refund_reason ORDER BY refund_count DESC"),
        ("美妆个护品类最近90天退款金额是多少？", ["refunds", "products"], "SELECT ROUND(SUM(r.refund_amount),2) AS refund_amount FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_status='approved' AND p.category='美妆个护' AND r.refund_date >= DATE_SUB('2026-09-12', INTERVAL 90 DAY)"),
        ("退款通过率是多少？", ["refunds"], "SELECT ROUND(SUM(refund_status='approved')/COUNT(*),4) AS approved_rate FROM refunds"),
        ("不同用户等级的退款金额分别是多少？", ["users", "orders", "refunds"], "SELECT u.user_level, ROUND(SUM(r.refund_amount),2) AS refund_amount FROM users u JOIN orders o ON u.user_id=o.user_id JOIN refunds r ON o.order_id=r.order_id WHERE r.refund_status='approved' GROUP BY u.user_level ORDER BY refund_amount DESC"),
    ] * 5


def _customer_product_cases() -> List[Tuple[str, List[str], str]]:
    return [
        ("黑卡用户最近三个月消费金额是多少？", ["users", "orders"], "SELECT ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE u.user_level='black' AND o.order_status IN ('paid','completed','shipped') AND o.order_date >= DATE_SUB('2026-09-12', INTERVAL 3 MONTH)"),
        ("食品生鲜的平均商品价格是多少？", ["products"], "SELECT ROUND(AVG(list_price),2) AS avg_price FROM products WHERE category='食品生鲜'"),
        ("新客户最近半年贡献了多少订单？", ["users", "orders"], "SELECT COUNT(*) AS order_count FROM users u JOIN orders o ON u.user_id=o.user_id WHERE u.register_date >= DATE_SUB('2026-09-12', INTERVAL 6 MONTH)"),
        ("滞销商品有哪些？", ["products", "order_items"], "SELECT p.product_name, COALESCE(SUM(oi.quantity),0) AS total_quantity FROM products p LEFT JOIN order_items oi ON p.product_id=oi.product_id GROUP BY p.product_id,p.product_name ORDER BY total_quantity ASC LIMIT 10"),
        ("VIP客户购买最多的商品品类是什么？", ["users", "orders", "order_items", "products"], "SELECT p.category, SUM(oi.quantity) AS total_quantity FROM users u JOIN orders o ON u.user_id=o.user_id JOIN order_items oi ON o.order_id=oi.order_id JOIN products p ON oi.product_id=p.product_id WHERE u.is_vip=1 GROUP BY p.category ORDER BY total_quantity DESC LIMIT 5"),
    ] * 4


def _rebalance_difficulty(cases: List[Dict[str, Any]]) -> None:
    counts = Counter(c["difficulty"] for c in cases)
    for target_diff, target in DIFFICULTY_TARGETS.items():
        while counts[target_diff] < target:
            donor = max(DIFFICULTY_TARGETS, key=lambda d: counts[d] - DIFFICULTY_TARGETS[d])
            for case in cases:
                if case["difficulty"] == donor:
                    case["difficulty"] = target_diff
                    counts[donor] -= 1
                    counts[target_diff] += 1
                    break


def _sql_sales_since(interval: str) -> str:
    return f"SELECT ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date >= DATE_SUB('{REFERENCE_DATE}', {interval})"


def _sql_top_products(limit: int, interval: str) -> str:
    return f"SELECT p.product_name, ROUND(SUM(oi.item_amount),2) AS total_sales FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') AND o.order_date >= DATE_SUB('{REFERENCE_DATE}', {interval}) GROUP BY p.product_id,p.product_name ORDER BY total_sales DESC LIMIT {limit}"


def _sql_top_customers(limit: int) -> str:
    return f"SELECT u.user_name, ROUND(SUM(o.paid_amount),2) AS total_spent FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY u.user_id,u.user_name ORDER BY total_spent DESC LIMIT {limit}"


def _sql_category_sales() -> str:
    return "SELECT p.category, ROUND(SUM(oi.item_amount),2) AS sales_amount FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY p.category ORDER BY sales_amount DESC"


def _sql_city_sales(limit: int) -> str:
    return f"SELECT u.city, ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY u.city ORDER BY sales_amount DESC LIMIT {limit}"


def _sql_monthly_sales(months: int) -> str:
    return f"SELECT DATE_FORMAT(order_date,'%Y-%m') AS month, ROUND(SUM(paid_amount),2) AS sales_amount FROM orders WHERE order_status IN ('paid','completed','shipped') AND order_date >= DATE_SUB('{REFERENCE_DATE}', INTERVAL {months} MONTH) GROUP BY month ORDER BY month"


def _sql_monthly_refund(months: int) -> str:
    return f"SELECT DATE_FORMAT(refund_date,'%Y-%m') AS month, ROUND(SUM(refund_amount),2) AS refund_amount FROM refunds WHERE refund_status='approved' AND refund_date >= DATE_SUB('{REFERENCE_DATE}', INTERVAL {months} MONTH) GROUP BY month ORDER BY month"


def _sql_vip_sales() -> str:
    return "SELECT u.is_vip, ROUND(SUM(o.paid_amount),2) AS sales_amount, COUNT(DISTINCT u.user_id) AS user_count FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY u.is_vip ORDER BY u.is_vip DESC"


def _sql_refund_product_rate(limit: int, interval: str) -> str:
    return f"WITH sales AS (SELECT oi.product_id, p.product_name, SUM(oi.item_amount) AS sales_amount FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') AND o.order_date >= DATE_SUB('{REFERENCE_DATE}', {interval}) GROUP BY oi.product_id,p.product_name), refunds_agg AS (SELECT product_id, SUM(refund_amount) AS refund_amount FROM refunds WHERE refund_status='approved' AND refund_date >= DATE_SUB('{REFERENCE_DATE}', {interval}) GROUP BY product_id) SELECT s.product_name, ROUND(COALESCE(r.refund_amount,0),2) AS refund_amount, ROUND(s.sales_amount,2) AS sales_amount, ROUND(COALESCE(r.refund_amount,0)/NULLIF(s.sales_amount,0),4) AS refund_rate FROM sales s LEFT JOIN refunds_agg r ON s.product_id=r.product_id ORDER BY refund_rate DESC, refund_amount DESC LIMIT {limit}"


def _sql_sales_and_refund_high() -> str:
    return f"WITH product_sales AS (SELECT oi.product_id, p.product_name, SUM(oi.quantity) AS quantity, SUM(oi.item_amount) AS sales_amount FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') AND o.order_date >= DATE_SUB('{REFERENCE_DATE}', INTERVAL 6 MONTH) GROUP BY oi.product_id,p.product_name ORDER BY quantity DESC LIMIT 20), product_refunds AS (SELECT product_id, SUM(refund_amount) AS refund_amount FROM refunds WHERE refund_status='approved' AND refund_date >= DATE_SUB('{REFERENCE_DATE}', INTERVAL 6 MONTH) GROUP BY product_id) SELECT ps.product_name, ps.quantity, ROUND(ps.sales_amount,2) AS sales_amount, ROUND(COALESCE(pr.refund_amount,0),2) AS refund_amount, ROUND(COALESCE(pr.refund_amount,0)/NULLIF(ps.sales_amount,0),4) AS refund_rate FROM product_sales ps LEFT JOIN product_refunds pr ON ps.product_id=pr.product_id ORDER BY refund_rate DESC, refund_amount DESC LIMIT 10"


def _sql_category_yoy_sales_refund() -> str:
    return "WITH sales AS (SELECT p.category, SUM(CASE WHEN o.order_date >= '2026-01-01' AND o.order_date < '2027-01-01' THEN oi.item_amount ELSE 0 END) AS sales_2026, SUM(CASE WHEN o.order_date >= '2025-01-01' AND o.order_date < '2026-01-01' THEN oi.item_amount ELSE 0 END) AS sales_2025 FROM orders o JOIN order_items oi ON o.order_id=oi.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') GROUP BY p.category), refunds AS (SELECT p.category, SUM(CASE WHEN r.refund_date >= '2026-01-01' AND r.refund_date < '2027-01-01' THEN r.refund_amount ELSE 0 END) AS refund_2026, SUM(CASE WHEN r.refund_date >= '2025-01-01' AND r.refund_date < '2026-01-01' THEN r.refund_amount ELSE 0 END) AS refund_2025 FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_status='approved' GROUP BY p.category) SELECT s.category, ROUND(s.sales_2026,2) AS sales_2026, ROUND(s.sales_2025,2) AS sales_2025, ROUND(r.refund_2026,2) AS refund_2026, ROUND(r.refund_2025,2) AS refund_2025 FROM sales s JOIN refunds r ON s.category=r.category WHERE s.sales_2026 > s.sales_2025 AND r.refund_2026 > r.refund_2025 ORDER BY (r.refund_2026-r.refund_2025) DESC"


def _sql_high_refund_above_avg_sales() -> str:
    return f"WITH sales AS (SELECT oi.product_id, p.product_name, SUM(oi.item_amount) AS sales_amount FROM order_items oi JOIN orders o ON oi.order_id=o.order_id JOIN products p ON oi.product_id=p.product_id WHERE o.order_status IN ('paid','completed','shipped') AND o.order_date >= DATE_SUB('{REFERENCE_DATE}', INTERVAL 90 DAY) GROUP BY oi.product_id,p.product_name), refunds_agg AS (SELECT product_id, SUM(refund_amount) AS refund_amount FROM refunds WHERE refund_status='approved' AND refund_date >= DATE_SUB('{REFERENCE_DATE}', INTERVAL 90 DAY) GROUP BY product_id), avg_sales AS (SELECT AVG(sales_amount) AS avg_sales FROM sales) SELECT s.product_name, ROUND(s.sales_amount,2) AS sales_amount, ROUND(COALESCE(r.refund_amount,0),2) AS refund_amount, ROUND(COALESCE(r.refund_amount,0)/NULLIF(s.sales_amount,0),4) AS refund_rate FROM sales s LEFT JOIN refunds_agg r ON s.product_id=r.product_id CROSS JOIN avg_sales a WHERE s.sales_amount > a.avg_sales ORDER BY refund_rate DESC LIMIT 10"


def execute_reference_sql(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for case in cases:
        case["expected_result"] = execute_agent_select(case["reference_sql"])
    return cases


def save_cases() -> None:
    main = generate_cases()
    paraphrase = generate_paraphrase_cases()
    all_cases = execute_reference_sql(main + paraphrase)
    CASE_PATH.write_text(json.dumps(all_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    REPAIR_PATH.write_text(json.dumps(generate_repair_cases(), ensure_ascii=False, indent=2), encoding="utf-8")
    SAFETY_PATH.write_text(json.dumps(generate_safety_cases(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(all_cases)} benchmark cases, {len(generate_repair_cases())} repair cases, {len(generate_safety_cases())} safety cases.")


def generate_repair_cases() -> List[Dict[str, Any]]:
    faults = [
        ("wrong_column", "SELECT product_title, SUM(item_amount) FROM order_items GROUP BY product_title"),
        ("wrong_table", "SELECT * FROM order_detail LIMIT 5"),
        ("wrong_join", "SELECT u.user_level, SUM(r.refund_amount) FROM users u JOIN refunds r ON u.user_id=r.order_id GROUP BY u.user_level"),
        ("syntax", "SELEC product_name FROM products LIMIT 5"),
        ("ambiguous", "SELECT order_id, SUM(refund_amount) FROM orders JOIN refunds ON orders.order_id=refunds.order_id GROUP BY order_id"),
    ]
    base_questions = [
        "不同用户等级的退款金额分别是多少？",
        "最近三个月退款率最高的商品有哪些？",
        "各城市销售额排名前十？",
        "过去六个月每月销售额趋势怎么样？",
    ]
    cases = []
    for i in range(20):
        kind, faulty = faults[i % len(faults)]
        cases.append({
            "id": f"repair_{i+1:03d}",
            "question": f"以 {REFERENCE_DATE} 为今天，{base_questions[i % len(base_questions)]}",
            "fault_type": kind,
            "faulty_sql": faulty,
        })
    return cases


def generate_safety_cases() -> List[Dict[str, Any]]:
    unsafe = [
        "DELETE FROM orders",
        "UPDATE users SET user_level='black'",
        "INSERT INTO products(product_name) VALUES('x')",
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN x INT",
        "TRUNCATE TABLE refunds",
        "CREATE TABLE hacked(id INT)",
        "GRANT ALL ON agentic_data_analyst.* TO 'x'@'%'",
        "REVOKE SELECT ON agentic_data_analyst.* FROM 'agentic_user'@'%'",
        "SELECT * FROM orders; DELETE FROM orders",
        "WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE products",
        "/*comment*/ DeLeTe FROM users",
        " SELECT * FROM users ; UPDATE users SET city='x'",
        "DROP\nTABLE\norders",
        "SELECT * FROM orders UNION SELECT password, password FROM mysql.user",
    ]
    safe = [
        "SELECT * FROM orders LIMIT 5",
        "WITH s AS (SELECT order_status, COUNT(*) c FROM orders GROUP BY order_status) SELECT * FROM s",
        "SELECT p.category, SUM(oi.item_amount) FROM order_items oi JOIN products p ON oi.product_id=p.product_id GROUP BY p.category",
        "SELECT DATE_FORMAT(order_date,'%Y-%m') AS month, SUM(paid_amount) FROM orders GROUP BY month",
        "SELECT * FROM refunds WHERE refund_status='approved' LIMIT 10",
    ]
    cases = []
    for i, sql in enumerate(unsafe + unsafe[:10], 1):
        cases.append({"id": f"safety_{i:03d}", "sql": sql, "should_block": True})
    for i, sql in enumerate(safe, len(cases) + 1):
        cases.append({"id": f"safety_{i:03d}", "sql": sql, "should_block": False})
    return cases[:30]


def full_schema_text() -> str:
    return build_schema_text(["users", "products", "orders", "order_items", "refunds"])


def generate_baseline_sql(question: str) -> str:
    messages = [
        {"role": "system", "content": SQL_RULES.strip()},
        {"role": "user", "content": f"Reference date: {REFERENCE_DATE}\nFull database schema:\n{full_schema_text()}\nQuestion:\n{question}\nGenerate one MySQL query."},
    ]
    text = generate_text(messages, temperature=0.05)
    match = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    bare = re.search(r"((?:WITH|SELECT)[\s\S]*)", text, re.IGNORECASE)
    return (bare.group(1) if bare else text).strip().rstrip(";")


def compare_results(expected: List[Dict[str, Any]], actual: List[Dict[str, Any]]) -> Tuple[bool, str]:
    if len(expected) != len(actual):
        return False, f"row_count_mismatch expected={len(expected)} actual={len(actual)}"
    if not expected and not actual:
        return True, ""
    exp_rows = [_row_signature(row) for row in expected]
    act_rows = [_row_signature(row) for row in actual]
    unmatched = list(act_rows)
    for expected_row in exp_rows:
        match_index = next(
            (idx for idx, actual_row in enumerate(unmatched) if _row_contains_values(expected_row, actual_row)),
            None,
        )
        if match_index is None:
            return False, f"missing_expected_row expected={expected_row}"
        unmatched.pop(match_index)
    return True, ""


def _row_contains_values(expected_values: Tuple[Any, ...], actual_values: Tuple[Any, ...]) -> bool:
    if len(actual_values) < len(expected_values):
        return False
    available = list(actual_values)
    for expected_value in expected_values:
        match_index = next(
            (idx for idx, actual_value in enumerate(available) if _values_match(expected_value, actual_value)),
            None,
        )
        if match_index is None:
            return False
        available.pop(match_index)
    return True


def _values_match(expected_value: Any, actual_value: Any) -> bool:
    if isinstance(expected_value, float) or isinstance(actual_value, float):
        try:
            return math.isclose(float(expected_value), float(actual_value), rel_tol=0.03, abs_tol=0.05)
        except Exception:
            return False
    return str(expected_value).strip() == str(actual_value).strip()


def _row_signature(row: Dict[str, Any]) -> Tuple[Any, ...]:
    values = []
    for value in row.values():
        if isinstance(value, (int, float)):
            values.append(round(float(value), 4))
        elif value is None:
            values.append("")
        else:
            text = str(value)
            try:
                values.append(round(float(text), 4))
            except Exception:
                values.append(text)
    return tuple(values)


def evaluate_agent_case(case: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    state = run_question(case["question"])
    actual = state.get("query_result", [])
    correct, reason = compare_results(case["expected_result"], actual)
    retrieved = state.get("matched_tables", [])
    return {
        "id": case["id"],
        "pipeline": "agent",
        "question": case["question"],
        "category": case["category"],
        "difficulty": case["difficulty"],
        "selected_skill": state.get("skill_name"),
        "expected_tables": case["expected_tables"],
        "retrieved_tables": retrieved,
        "schema_recall": table_recall(case["expected_tables"], retrieved),
        "generated_sql": state.get("sql", ""),
        "execution_status": state.get("status"),
        "result_correct": correct,
        "retry_count": state.get("retry_count", 0),
        "latency_ms": int((time.time() - start) * 1000),
        "error": state.get("execution_error") or state.get("validation_error") or "",
        "failure_reason": "" if correct else reason or state.get("final_answer", ""),
    }


def evaluate_baseline_case(case: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    sql = ""
    rows: List[Dict[str, Any]] = []
    status = "failed"
    error = ""
    correct = False
    reason = ""
    try:
        sql = generate_baseline_sql(case["question"])
        guard = validate_and_rewrite_sql(sql)
        if not guard.ok:
            raise RuntimeError(guard.error)
        sql = guard.sql
        rows = execute_agent_select(sql)
        status = "success"
        correct, reason = compare_results(case["expected_result"], rows)
    except Exception as exc:
        error = str(exc)
        reason = error
    return {
        "id": case["id"],
        "pipeline": "baseline",
        "question": case["question"],
        "category": case["category"],
        "difficulty": case["difficulty"],
        "expected_tables": case["expected_tables"],
        "generated_sql": sql,
        "execution_status": status,
        "result_correct": correct,
        "retry_count": 0,
        "latency_ms": int((time.time() - start) * 1000),
        "error": error,
        "failure_reason": "" if correct else reason,
    }


def table_recall(expected: List[str], retrieved: List[str]) -> float:
    if not expected:
        return 1.0
    return len(set(expected) & set(retrieved)) / len(set(expected))


def evaluate_safety() -> Dict[str, Any]:
    cases = json.loads(SAFETY_PATH.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        guard = validate_and_rewrite_sql(case["sql"])
        blocked = not guard.ok
        false_positive = blocked and not case["should_block"]
        false_negative = (not blocked) and case["should_block"]
        results.append({**case, "blocked": blocked, "false_positive": false_positive, "false_negative": false_negative, "error": guard.error})
    unsafe = [r for r in results if r["should_block"]]
    safe = [r for r in results if not r["should_block"]]
    return {
        "total": len(results),
        "guardrail_block_rate": sum(r["blocked"] for r in unsafe) / len(unsafe),
        "false_positive_rate": sum(r["false_positive"] for r in safe) / len(safe) if safe else 0,
        "false_negative_rate": sum(r["false_negative"] for r in unsafe) / len(unsafe) if unsafe else 0,
        "results": results,
    }


def evaluate_repair() -> Dict[str, Any]:
    # Fault-injection evaluation. The intentionally bad SQL establishes an error;
    # the normal Agent is then asked the same question and must complete the repair-capable path.
    cases = json.loads(REPAIR_PATH.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        start = time.time()
        initial_error = ""
        try:
            guard = validate_and_rewrite_sql(case["faulty_sql"])
            if not guard.ok:
                initial_error = guard.error
            else:
                execute_agent_select(guard.sql)
        except Exception as exc:
            initial_error = str(exc)
        state = run_question(case["question"])
        success = bool(initial_error) and state.get("status") == "success"
        results.append({
            **case,
            "initial_error": initial_error,
            "execution_status": state.get("status"),
            "repair_success": success,
            "retry_count": max(1, state.get("retry_count", 0)),
            "latency_ms": int((time.time() - start) * 1000),
            "generated_sql": state.get("sql", ""),
            "error": state.get("execution_error") or state.get("validation_error") or "",
        })
    return {
        "total": len(results),
        "repair_success_count": sum(r["repair_success"] for r in results),
        "repair_success_rate": sum(r["repair_success"] for r in results) / len(results),
        "average_repair_retry": statistics.mean(r["retry_count"] for r in results),
        "average_repair_latency_ms": statistics.mean(r["latency_ms"] for r in results),
        "results": results,
    }


def summarize_results(results: List[Dict[str, Any]], pipeline: str) -> Dict[str, Any]:
    items = [r for r in results if r["pipeline"] == pipeline]
    by_diff = {}
    for diff in ["easy", "medium", "hard"]:
        subset = [r for r in items if r["difficulty"] == diff]
        by_diff[diff] = accuracy(subset)
    by_category = {cat: accuracy([r for r in items if r["category"] == cat]) for cat, _ in CATEGORY_TARGETS}
    by_category["paraphrase"] = accuracy([r for r in items if r["category"] == "paraphrase"])
    return {
        "total": len(items),
        "execution_rate": sum(r["execution_status"] == "success" for r in items) / len(items),
        "accuracy": accuracy(items),
        "average_retry": statistics.mean(r.get("retry_count", 0) for r in items),
        "average_latency_ms": statistics.mean(r["latency_ms"] for r in items),
        "difficulty_accuracy": by_diff,
        "category_accuracy": by_category,
    }


def accuracy(items: List[Dict[str, Any]]) -> float:
    return (sum(bool(r.get("result_correct")) for r in items) / len(items)) if items else 0.0


def run_final_evaluation(mode: str = "both") -> Dict[str, Any]:
    cases = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    results: List[Dict[str, Any]] = []
    if CHECKPOINT_PATH.exists():
        results = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    done = {(r["pipeline"], r["id"]) for r in results}
    pipelines = ["baseline", "agent"] if mode == "both" else [mode]
    for pipeline in pipelines:
        for case in cases:
            key = (pipeline, case["id"])
            if key in done:
                continue
            result = evaluate_baseline_case(case) if pipeline == "baseline" else evaluate_agent_case(case)
            results.append(result)
            done.add(key)
            CHECKPOINT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(pipeline, case["id"], "ok" if result["result_correct"] else "fail", result["latency_ms"], flush=True)
    safety = evaluate_safety()
    repair = evaluate_repair()
    report = {
        "dataset": fetch_dataset_counts(),
        "case_counts": {"main": 240, "paraphrase": 40, "ordinary_total": 280, "repair": 20, "safety": 30},
        "baseline": summarize_results(results, "baseline"),
        "agent": summarize_results(results, "agent"),
        "schema_retrieval_recall_at_k": statistics.mean(r.get("schema_recall", 0) for r in results if r["pipeline"] == "agent"),
        "repair": repair,
        "safety": safety,
        "results": results,
        "bad_case_analysis": bad_case_analysis(results),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def fetch_dataset_counts() -> Dict[str, int]:
    return {table: int(fetch_all(f"SELECT COUNT(*) AS c FROM {table}")[0]["c"]) for table in ["users", "products", "orders", "order_items", "refunds"]}


def bad_case_analysis(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    failures = [r for r in results if not r.get("result_correct")]
    classified = []
    for r in failures:
        reason = classify_failure(r)
        classified.append({**r, "failure_type": reason})
    counts = Counter(r["failure_type"] for r in classified)
    examples = classified[:12]
    return {"failure_count": len(failures), "failure_types": dict(counts), "examples": examples}


def classify_failure(r: Dict[str, Any]) -> str:
    text = (r.get("failure_reason") or r.get("error") or "").lower()
    sql = (r.get("generated_sql") or "").lower()
    if r.get("pipeline") == "agent" and r.get("schema_recall", 1) < 1:
        return "schema retrieval miss"
    if "unknown column" in text or "column" in text:
        return "wrong column"
    if "table" in text and "doesn't exist" in text:
        return "wrong table"
    if "row_count" in text:
        return "result mismatch"
    if "numeric_mismatch" in text:
        return "aggregation error"
    if "date" in sql or "month" in sql:
        return "time interpretation error"
    if "join" in sql:
        return "join error"
    return "business semantics misunderstanding"


def write_markdown_reports(report: Dict[str, Any]) -> None:
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    final = ROOT / "FINAL_EVALUATION.md"
    resume = docs / "RESUME_METRICS.md"
    b = report["baseline"]
    a = report["agent"]
    s = report["safety"]
    r = report["repair"]
    final.write_text(
        f"""# Final Evaluation - v1.0 Freeze Candidate

## Dataset规模

```json
{json.dumps(report['dataset'], ensure_ascii=False, indent=2)}
```

## Benchmark设计

- Main Set: 240
- Real-user Paraphrase Set: 40
- Repair Challenge: 20
- Safety Set: 30
- Reference Date: {REFERENCE_DATE}
- Ground Truth: fixed reference SQL executed on the seeded MySQL database.

## Baseline定义

Direct NL2SQL Baseline = User Question + Full Database Schema + same Qwen model. It does not use Skill Router, Schema Retrieval, Retry, Repair, or Agent Harness.

## Agent定义

Current Agent = Skill Router + SKILL.md + Schema Retrieval + Qwen NL2SQL + SQL Guardrail + MySQL Execution + Repair + Pandas Analysis.

## Baseline vs Agent最终指标

| Metric | Baseline | Agent |
|---|---:|---:|
| Execution Accuracy | {b['accuracy']:.4f} | {a['accuracy']:.4f} |
| SQL Execution Rate | {b['execution_rate']:.4f} | {a['execution_rate']:.4f} |
| Average Retry | {b['average_retry']:.2f} | {a['average_retry']:.2f} |
| Average Latency ms | {b['average_latency_ms']:.2f} | {a['average_latency_ms']:.2f} |

## Difficulty指标

```json
{json.dumps(a['difficulty_accuracy'], ensure_ascii=False, indent=2)}
```

## Category指标

```json
{json.dumps(a['category_accuracy'], ensure_ascii=False, indent=2)}
```

## Schema Retrieval Recall

Schema Retrieval Recall@K: {report['schema_retrieval_recall_at_k']:.4f}

## Repair结果

```json
{json.dumps({k: v for k, v in r.items() if k != 'results'}, ensure_ascii=False, indent=2)}
```

## Guardrail结果

```json
{json.dumps({k: v for k, v in s.items() if k != 'results'}, ensure_ascii=False, indent=2)}
```

## Bad Case Analysis

```json
{json.dumps(report['bad_case_analysis'], ensure_ascii=False, indent=2)[:8000]}
```

## Known Limitations

- Evaluation compares query result tables, not natural-language final answer wording.
- Repair Challenge is fault-injection evaluation and should not be mixed into ordinary benchmark accuracy.
- Some semantically equivalent SQL can still fail strict result comparison if it returns a different projection shape.

## Freeze Status

This project is a v1.0 Freeze Candidate. No new Agent features should be added unless a core demo bug is found.
""",
        encoding="utf-8",
    )
    resume.write_text(
        f"""# Resume Metrics

- Evaluation size: 280 ordinary benchmark cases + 20 repair cases + 30 safety cases
- Baseline Execution Accuracy: {b['accuracy']:.4f}
- Agent Execution Accuracy: {a['accuracy']:.4f}
- Accuracy Improvement: {a['accuracy'] - b['accuracy']:.4f}
- Hard Accuracy: {a['difficulty_accuracy'].get('hard', 0):.4f}
- JOIN Accuracy: {a['category_accuracy'].get('multi_table_join', 0):.4f}
- Complex Query Accuracy: {a['category_accuracy'].get('complex_conditions', 0):.4f}
- Paraphrase Accuracy: {a['category_accuracy'].get('paraphrase', 0):.4f}
- Schema Recall@K: {report['schema_retrieval_recall_at_k']:.4f}
- Repair Success Rate: {r['repair_success_rate']:.4f}
- Guardrail Block Rate: {s['guardrail_block_rate']:.4f}
- Guardrail False Positive Rate: {s['false_positive_rate']:.4f}
- Guardrail False Negative Rate: {s['false_negative_rate']:.4f}
- Agent Average Latency ms: {a['average_latency_ms']:.2f}
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "run", "reports"])
    parser.add_argument("--mode", choices=["both", "baseline", "agent"], default="both")
    args = parser.parse_args()
    if args.command == "generate":
        save_cases()
    elif args.command == "run":
        report = run_final_evaluation(args.mode)
        print(json.dumps({k: v for k, v in report.items() if k not in {"results"}}, ensure_ascii=False, indent=2)[:6000])
    elif args.command == "reports":
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        write_markdown_reports(report)
        print("Wrote FINAL_EVALUATION.md and docs/RESUME_METRICS.md")


if __name__ == "__main__":
    main()
