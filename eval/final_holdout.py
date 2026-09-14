"""Generate and freeze the final 250-case business holdout before model runs."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.daily_business import digest, fingerprint, write_json


REFERENCE_DATE = "2026-09-12"
SEED = 20260914
VALID = "order_status IN ('paid','completed','shipped')"
CASE_PATH = ROOT / "eval/final_holdout_cases.json"
MANIFEST_PATH = ROOT / "eval/final_holdout_manifest.json"


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def add(category, difficulty, question, sql, tables, spoken=None, ordered=False):
        cases.append(
            {
                "difficulty": difficulty,
                "category": category,
                "question": f"以 {REFERENCE_DATE} 为今天，{spoken or question}",
                "reference_sql": sql,
                "expected_tables": tables,
                "ordered": ordered,
                "paraphrase": spoken is not None,
                "reference_date": REFERENCE_DATE,
            }
        )

    categories = ["家用电器", "手机数码", "服饰鞋包", "母婴用品", "美妆个护", "运动户外", "食品生鲜"]
    prices = [95, 275, 525, 975, 1875]
    for category in categories:
        for index, price in enumerate(prices):
            add(
                "filtering_aggregation",
                "easy",
                f"{category}中仍在销售且成本价不低于{price}元的商品有多少种？",
                f"SELECT COUNT(*) AS product_count FROM products WHERE category='{category}' AND is_active=1 AND cost_price>={price}",
                ["products"],
                spoken=f"数一下{category}现在还卖着的商品，成本至少{price}元的有多少种？" if index == 0 and category in categories[:5] else None,
            )
    cities = ["上海市", "北京市", "南京市", "广州市", "成都市", "杭州市", "武汉市", "西安市"]
    user_specs = [
        ("VIP用户", "is_vip=1"),
        ("2024年7月1日之后注册的用户", "register_date>='2024-07-01'"),
        ("金卡或黑卡用户", "user_level IN ('gold','black')"),
    ]
    for city in cities:
        for index, (label, condition) in enumerate(user_specs):
            add(
                "filtering_aggregation",
                "easy",
                f"{city}的{label}有多少人？",
                f"SELECT COUNT(*) AS user_count FROM users WHERE city='{city}' AND {condition}",
                ["users"],
                spoken=f"{city}现在有多少位VIP客户？" if index == 0 and city == "上海市" else None,
            )
    order_metrics = [
        ("有效订单数", "COUNT(*)"),
        ("有效订单销售额", "ROUND(SUM(paid_amount),2)"),
        ("有效订单平均实付金额", "ROUND(AVG(paid_amount),2)"),
        ("有效订单优惠金额合计", "ROUND(SUM(discount_amount),2)"),
    ]
    for method in ["alipay", "wechat", "card", "cash"]:
        for label, expression in order_metrics:
            add(
                "filtering_aggregation",
                "easy",
                f"使用{method}支付的{label}是多少？",
                f"SELECT {expression} AS value FROM orders WHERE {VALID} AND payment_method='{method}'",
                ["orders"],
            )

    ranking_specs = [(4, "DESC", "最高"), (7, "ASC", "最低"), (11, "DESC", "最高"), (13, "ASC", "最低"), (17, "DESC", "最高")]
    for category in categories[:5]:
        for index, (limit, direction, label) in enumerate(ranking_specs):
            add(
                "top_k_ranking",
                "easy",
                f"{category}在售商品中成本价{label}的{limit}种是什么？返回商品名称和成本价，同价时按商品ID升序。",
                f"SELECT product_name,cost_price FROM products WHERE category='{category}' AND is_active=1 ORDER BY cost_price {direction},product_id ASC LIMIT {limit}",
                ["products"],
                spoken=f"{category}还在卖的商品里，成本最{('高' if direction == 'DESC' else '低')}的{limit}种给我，重名次按商品ID从小到大。" if index == 0 else None,
                ordered=True,
            )
    windows = [24, 39, 66, 108, 156]
    limits = [4, 7, 11, 13, 17]
    customer_metrics = [
        ("消费总额", "ROUND(SUM(o.paid_amount),2)"),
        ("有效订单数", "COUNT(*)"),
        ("平均订单实付金额", "ROUND(AVG(o.paid_amount),2)"),
        ("消费总额", "ROUND(SUM(o.paid_amount),2)"),
        ("有效订单数", "COUNT(*)"),
    ]
    for row, days in enumerate(windows):
        for column, limit in enumerate(limits):
            label, expression = customer_metrics[column]
            add(
                "top_k_ranking",
                "medium",
                f"最近{days}天按{label}从高到低列出前{limit}位客户，返回客户名称和该指标，同值按用户ID升序。",
                f"SELECT u.user_name,{expression} AS metric FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.user_id,u.user_name ORDER BY metric DESC,u.user_id ASC LIMIT {limit}",
                ["users", "orders"],
                spoken=f"近{days}天谁花得最多？给我前{limit}位客户和实付总额，同金额按用户ID排。" if row == 0 and column == 0 else None,
                ordered=True,
            )

    time_windows = [9, 23, 41, 73, 137]
    time_metrics = [
        ("有效订单数", "COUNT(*)"),
        ("销售额", "ROUND(SUM(paid_amount),2)"),
        ("平均实付金额", "ROUND(AVG(paid_amount),2)"),
        ("付费用户数", "COUNT(DISTINCT user_id)"),
        ("优惠金额合计", "ROUND(SUM(discount_amount),2)"),
    ]
    for days in time_windows:
        for index, (label, expression) in enumerate(time_metrics):
            add(
                "time_trend",
                "easy",
                f"过去{days}天的{label}是多少？只统计有效订单。",
                f"SELECT {expression} AS value FROM orders WHERE {VALID} AND order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY)",
                ["orders"],
                spoken=f"近{days}天成交了多少笔有效订单？" if index == 0 and days in time_windows[:3] else None,
            )
    starts = ["2024-11-01", "2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01"]
    for start in starts:
        for index, (label, expression) in enumerate(time_metrics):
            add(
                "time_trend",
                "medium",
                f"从{start}到2026年9月1日之前，逐月统计有效订单的{label}，返回月份和指标并按月份升序。",
                f"SELECT DATE_FORMAT(order_date,'%Y-%m') AS month,{expression} AS value FROM orders WHERE {VALID} AND order_date>='{start}' AND order_date<'2026-09-01' GROUP BY month ORDER BY month",
                ["orders"],
                spoken=f"从{start}起到今年9月前，每个月成交多少笔？按月份顺着列。" if index == 0 and start in starts[:3] else None,
                ordered=True,
            )

    join_windows = [17, 31, 47, 69, 93, 129, 183, 271]
    dimensions = [("city", "城市"), ("province", "省份"), ("user_level", "用户等级"), ("is_vip", "VIP标记")]
    for days in join_windows:
        for index, (field, label) in enumerate(dimensions):
            add(
                "one_two_table_join",
                "medium",
                f"最近{days}天按{label}汇总有效订单数、销售额和付费用户数，返回{label}和三个指标。",
                f"SELECT u.{field},COUNT(*) AS order_count,ROUND(SUM(o.paid_amount),2) AS sales_amount,COUNT(DISTINCT o.user_id) AS paying_users FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.{field}",
                ["users", "orders"],
                spoken=f"近{days}天各{label}成交得怎么样？列出订单数、实付总额和付费客户数。" if days == 17 else None,
            )
    for days in [44, 88, 132]:
        for field, label in [("category", "商品品类"), ("brand", "品牌")]:
            add(
                "one_two_table_join",
                "medium",
                f"最近{days}天按{label}汇总已通过退款记录数、退款金额和涉及商品数。",
                f"SELECT p.{field},COUNT(*) AS refund_count,ROUND(SUM(r.refund_amount),2) AS refund_amount,COUNT(DISTINCT r.product_id) AS product_count FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_status='approved' AND r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.{field}",
                ["refunds", "products"],
                spoken=f"近{days}天各{label}实际退了多少？给退款笔数、金额和涉及商品数。" if days == 44 else None,
            )

    refund_windows = [29, 53, 77, 101, 149, 211]
    for days in refund_windows:
        for index, (field, label) in enumerate([("category", "商品品类"), ("brand", "品牌")]):
            add(
                "refund_customer_product",
                "medium",
                f"最近{days}天{label}中已通过退款金额最高的前8名是什么？返回{label}、退款金额和退款记录数，同金额按{label}升序。",
                f"SELECT p.{field},ROUND(SUM(r.refund_amount),2) AS refund_amount,COUNT(*) AS refund_count FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_status='approved' AND r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.{field} ORDER BY refund_amount DESC,p.{field} ASC LIMIT 8",
                ["refunds", "products"],
                spoken=f"近{days}天哪些{label}退的钱最多？看前8名和退款笔数，同金额按名称排。" if days in (29, 53) and index == 0 else None,
                ordered=True,
            )
    approval_windows = [33, 57, 81, 105, 133, 165, 201, 237, 273, 309, 345, 381, 417]
    for index, days in enumerate(approval_windows):
        field, label = (("category", "商品品类") if index % 2 == 0 else ("brand", "品牌"))
        add(
            "refund_customer_product",
            "hard",
            f"最近{days}天各{label}的退款通过率是多少？通过率为approved退款记录数除以该{label}全部退款记录数。返回{label}和通过率，保留4位并按通过率降序、{label}升序。",
            f"SELECT p.{field},ROUND(SUM(r.refund_status='approved')/COUNT(*),4) AS approval_rate FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.{field} ORDER BY approval_rate DESC,p.{field} ASC",
            ["refunds", "products"],
            spoken=f"近{days}天各{label}申请退款后有多少比例通过？按通过率从高到低列，同率按名称排。" if index < 2 else None,
            ordered=True,
        )

    for index, (days, minimum) in enumerate([(27, 650), (51, 1150), (79, 1850), (117, 2650), (163, 3850), (229, 5200)]):
        add(
            "complex",
            "hard",
            f"最近{days}天实付金额至少{minimum}元的有效订单里，找出没有任何approved退款记录的订单。返回订单ID和实付金额，按实付金额降序、订单ID升序，最多100条。",
            f"SELECT o.order_id,o.paid_amount FROM orders o WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) AND o.paid_amount>={minimum} AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.order_id=o.order_id AND r.refund_status='approved') ORDER BY o.paid_amount DESC,o.order_id ASC LIMIT 100",
            ["orders", "refunds"],
            spoken=f"近{days}天的大额成交单里，哪些一笔通过的退款都没有？门槛{minimum}元，按实付从高到低给我100条。" if index == 0 else None,
            ordered=True,
        )
    for index, (days, count, amount) in enumerate([(46, 2, 1800), (74, 3, 3200), (122, 4, 5100), (188, 5, 7600), (266, 6, 9800), (358, 7, 12500)]):
        add(
            "complex",
            "hard",
            f"最近{days}天至少完成{count}笔有效订单且消费总额不少于{amount}元的客户有哪些？返回客户名称、订单数和消费总额，按消费总额降序、用户ID升序，最多200位。",
            f"SELECT u.user_name,COUNT(*) AS order_count,ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.user_id,u.user_name HAVING COUNT(*)>={count} AND SUM(o.paid_amount)>={amount} ORDER BY sales_amount DESC,u.user_id ASC LIMIT 200",
            ["users", "orders"],
            spoken=f"近{days}天既买得勤又花得多的客户都有谁？至少{count}笔、总额不低于{amount}元，按消费倒排。" if index == 0 else None,
            ordered=True,
        )

    random.Random(SEED).shuffle(cases)
    for index, case in enumerate(cases, 1):
        case["id"] = f"final_holdout_{index:03}"
    return cases


def freeze() -> None:
    from app.tools.database import fetch_all

    if CASE_PATH.exists() or MANIFEST_PATH.exists():
        raise RuntimeError("Final holdout already exists; refusing to overwrite it")
    cases = build_cases()
    old_cases = json.loads((ROOT / "eval/daily_business_cases.json").read_text())
    assert len(cases) == 250
    assert len({case["question"] for case in cases}) == 250
    assert not ({case["question"] for case in cases} & {case["question"] for case in old_cases})
    assert Counter(case["difficulty"] for case in cases) == Counter({"easy": 125, "medium": 100, "hard": 25})
    assert Counter(case["category"] for case in cases) == Counter(
        {
            "filtering_aggregation": 75,
            "top_k_ranking": 50,
            "time_trend": 50,
            "one_two_table_join": 38,
            "refund_customer_product": 25,
            "complex": 12,
        }
    )
    assert sum(case["paraphrase"] for case in cases) == 30
    before = fingerprint(fetch_all)
    for case in cases:
        case["ground_truth_result"] = fetch_all(case["reference_sql"])
        assert len(case["ground_truth_result"]) <= 200
    assert before == fingerprint(fetch_all)
    write_json(CASE_PATH, cases)
    write_json(
        MANIFEST_PATH,
        {
            "status": "FINAL HOLDOUT FROZEN",
            "seed": SEED,
            "case_count": 250,
            "cases_sha256": digest(cases),
            "database": before,
            "reference_date": REFERENCE_DATE,
            "difficulty_counts": dict(Counter(case["difficulty"] for case in cases)),
            "category_counts": dict(Counter(case["category"] for case in cases)),
            "paraphrase_count": 30,
            "empty_result_count": sum(not case["ground_truth_result"] for case in cases),
            "scoring": "Same strict comparator as Daily Business Benchmark: exact rows/columns, numeric abs_tol 0.005, ordered cases enforce order.",
        },
    )
    print(json.dumps({"cases": 250, "paraphrase": 30, "sha256": digest(cases)}))


if __name__ == "__main__":
    freeze()
