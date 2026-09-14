"""Generate the unseen Final Holdout v2 after both systems are frozen."""

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
SEED = 20260915
VALID = "order_status IN ('paid','completed','shipped')"
CASE_PATH = ROOT / "eval/final_holdout_v2_cases.json"
MANIFEST_PATH = ROOT / "eval/final_holdout_v2_manifest.json"


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def add(category, difficulty, question, sql, tables, spoken=None, ordered=False):
        cases.append(
            {
                "difficulty": difficulty,
                "category": category,
                "question": f"以 {REFERENCE_DATE} 为今天，{spoken or question}",
                "reference_sql": sql,
                "ground_truth_result": None,
                "expected_tables": tables,
                "ordered": ordered,
                "paraphrase": spoken is not None,
                "reference_date": REFERENCE_DATE,
            }
        )

    categories = ["家用电器", "手机数码", "服饰鞋包", "母婴用品", "美妆个护"]
    product_metrics = [
        ("在售商品数", "COUNT(*)"),
        ("在售商品平均标价", "ROUND(AVG(list_price),2)"),
        ("在售商品平均成本价", "ROUND(AVG(cost_price),2)"),
        ("2025年以来上架的在售商品数", "SUM(launch_date>='2025-01-01')"),
        ("在售商品平均标价与成本价差额", "ROUND(AVG(list_price-cost_price),2)"),
    ]
    for category in categories:
        for index, (label, expression) in enumerate(product_metrics):
            add(
                "filtering_aggregation", "easy", f"{category}的{label}是多少？",
                f"SELECT {expression} AS value FROM products WHERE category='{category}' AND is_active=1",
                ["products"],
                spoken=f"看一下{category}现在还卖着的商品一共有多少种。" if index == 0 else None,
            )
    cities = ["上海市", "北京市", "南京市", "广州市", "成都市"]
    user_segments = [
        ("全部用户数", "1=1", "COUNT(*)"),
        ("VIP用户数", "is_vip=1", "COUNT(*)"),
        ("金卡用户数", "user_level='gold'", "COUNT(*)"),
        ("2025年注册用户数", "register_date>='2025-01-01' AND register_date<'2026-01-01'", "COUNT(*)"),
        ("银卡或金卡非VIP用户数", "is_vip=0 AND user_level IN ('silver','gold')", "COUNT(*)"),
    ]
    for city in cities:
        for index, (label, condition, expression) in enumerate(user_segments):
            add(
                "filtering_aggregation", "easy", f"{city}的{label}是多少？",
                f"SELECT {expression} AS value FROM users WHERE city='{city}' AND {condition}",
                ["users"],
                spoken=f"{city}客户库里现在有多少人？" if city == "上海市" and index == 0 else None,
            )
    status_metrics = [
        ("订单数", "COUNT(*)"),
        ("原始金额合计", "ROUND(SUM(gross_amount),2)"),
        ("优惠金额合计", "ROUND(SUM(discount_amount),2)"),
        ("实付金额合计", "ROUND(SUM(paid_amount),2)"),
        ("平均优惠金额", "ROUND(AVG(discount_amount),2)"),
    ]
    for status in ["paid", "completed", "shipped", "cancelled", "unpaid"]:
        for label, expression in status_metrics:
            add(
                "filtering_aggregation", "easy", f"状态为{status}的订单{label}是多少？",
                f"SELECT {expression} AS value FROM orders WHERE order_status='{status}'",
                ["orders"],
            )

    product_rankings = [
        (5, "list_price", "DESC", "标价最高"),
        (4, "cost_price", "ASC", "成本价最低"),
        (6, "list_price-cost_price", "DESC", "标价与成本价差额最大"),
        (8, "launch_date", "DESC", "上架时间最新"),
        (3, "launch_date", "ASC", "上架时间最早"),
    ]
    for category in categories:
        for index, (limit, expression, direction, label) in enumerate(product_rankings):
            output = "product_name,launch_date" if expression == "launch_date" else f"product_name,{expression} AS metric"
            add(
                "top_k_ranking", "easy",
                f"{category}在售商品中{label}的前{limit}种是什么？返回商品名称和排名指标，同值按商品ID升序。",
                f"SELECT {output} FROM products WHERE category='{category}' AND is_active=1 ORDER BY {expression} {direction},product_id ASC LIMIT {limit}",
                ["products"],
                spoken=f"{category}里现在哪{limit}款标价最贵？给名称和价格，同价按商品ID排。" if index == 0 else None,
                ordered=True,
            )
    customer_windows = [36, 62, 94, 146, 218]
    customer_rankings = [
        (5, "ROUND(AVG(o.paid_amount),2)", "平均订单实付金额"),
        (7, "ROUND(SUM(o.discount_amount),2)", "优惠金额合计"),
        (9, "COUNT(*)", "有效订单数"),
        (6, "ROUND(MAX(o.paid_amount),2)", "单笔最高实付金额"),
        (8, "COUNT(DISTINCT o.payment_method)", "使用过的支付方式数量"),
    ]
    for row, days in enumerate(customer_windows):
        for column, (limit, expression, label) in enumerate(customer_rankings):
            add(
                "top_k_ranking", "medium",
                f"最近{days}天按{label}从高到低列出前{limit}位用户，返回用户名称和指标，同值按用户ID升序。",
                f"SELECT u.user_name,{expression} AS metric FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.user_id,u.user_name ORDER BY metric DESC,u.user_id ASC LIMIT {limit}",
                ["users", "orders"],
                spoken=f"近{days}天客单价最高的是哪些用户？看前{limit}名，同值按用户ID。" if row == 0 and column == 0 else None,
                ordered=True,
            )

    named_windows = [
        ("今天", "order_date>='2026-09-12' AND order_date<'2026-09-13'"),
        ("昨天", "order_date>='2026-09-11' AND order_date<'2026-09-12'"),
        ("本月", "order_date>='2026-09-01' AND order_date<'2026-10-01'"),
        ("上月", "order_date>='2026-08-01' AND order_date<'2026-09-01'"),
        ("2026年第二季度", "order_date>='2026-04-01' AND order_date<'2026-07-01'"),
    ]
    time_metrics = [
        ("有效订单数", "COUNT(*)"),
        ("销售额", "ROUND(SUM(paid_amount),2)"),
        ("平均实付金额", "ROUND(AVG(paid_amount),2)"),
        ("付费用户数", "COUNT(DISTINCT user_id)"),
        ("优惠金额合计", "ROUND(SUM(discount_amount),2)"),
    ]
    for window_index, (window, condition) in enumerate(named_windows):
        for metric_index, (label, expression) in enumerate(time_metrics):
            add(
                "time_trend", "easy", f"{window}的{label}是多少？只统计有效订单。",
                f"SELECT {expression} AS value FROM orders WHERE {VALID} AND {condition}",
                ["orders"],
                spoken=f"帮我看下{window}成交了多少笔。" if metric_index == 0 and window_index < 3 else None,
            )
    daily_windows = [15, 28, 46, 67, 89]
    for window_index, days in enumerate(daily_windows):
        for metric_index, (label, expression) in enumerate(time_metrics):
            add(
                "time_trend", "medium",
                f"最近{days}天按日统计{label}，只统计有效订单；返回日期和指标，按日期升序。",
                f"SELECT order_date,{expression} AS value FROM orders WHERE {VALID} AND order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY order_date ORDER BY order_date",
                ["orders"],
                spoken=f"近{days}天每天成交多少单？日期从早到晚列。" if metric_index == 0 and window_index < 3 else None,
                ordered=True,
            )

    join_windows = [19, 43, 71, 109, 151, 203, 287, 365]
    dimensions = [("city", "城市"), ("province", "省份"), ("user_level", "用户等级"), ("is_vip", "VIP标记")]
    for days in join_windows:
        for field, label in dimensions:
            add(
                "one_two_table_join", "medium",
                f"最近{days}天按{label}统计有效订单原始金额、优惠金额、实付金额和平均实付金额。",
                f"SELECT u.{field},ROUND(SUM(o.gross_amount),2) AS gross_amount,ROUND(SUM(o.discount_amount),2) AS discount_amount,ROUND(SUM(o.paid_amount),2) AS paid_amount,ROUND(AVG(o.paid_amount),2) AS average_paid FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.{field}",
                ["users", "orders"],
                spoken=f"近{days}天各{label}的订单原价、优惠、实付和平均实付各是多少？" if days == 19 else None,
            )
    for days in [58, 116, 232]:
        for field, label in [("category", "商品品类"), ("brand", "品牌")]:
            add(
                "one_two_table_join", "medium",
                f"最近{days}天按{label}统计rejected退款数、pending退款数和approved退款金额。",
                f"SELECT p.{field},SUM(r.refund_status='rejected') AS rejected_count,SUM(r.refund_status='pending') AS pending_count,ROUND(SUM(CASE WHEN r.refund_status='approved' THEN r.refund_amount ELSE 0 END),2) AS approved_amount FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.{field}",
                ["refunds", "products"],
                spoken=f"近{days}天各{label}退款里，拒绝多少笔、待处理多少笔、实际通过多少钱？" if days == 58 else None,
            )

    product_segments = ["家用电器", "手机数码", "服饰鞋包", "母婴用品", "美妆个护", "运动户外"]
    for category in product_segments:
        for index, (field, label) in enumerate([("brand", "品牌"), ("is_active", "在售状态")]):
            add(
                "refund_customer_product", "medium",
                f"{category}按{label}汇总商品数、平均标价、平均成本价和平均价差。",
                f"SELECT {field},COUNT(*) AS product_count,ROUND(AVG(list_price),2) AS average_list_price,ROUND(AVG(cost_price),2) AS average_cost_price,ROUND(AVG(list_price-cost_price),2) AS average_gap FROM products WHERE category='{category}' GROUP BY {field}",
                ["products"],
                spoken=f"{category}各品牌有多少款，平均卖价、成本和价差分别多少？" if category in product_segments[:2] and index == 0 else None,
            )
    repeat_windows = [45, 75, 105, 135, 195, 255, 335]
    for index, days in enumerate(repeat_windows):
        add(
            "refund_customer_product", "hard",
            f"最近{days}天按用户等级计算复购用户率：至少2笔有效订单的用户数除以至少1笔有效订单的用户数。返回用户等级和复购率，保留4位。",
            f"WITH user_orders AS (SELECT u.user_level,o.user_id,COUNT(*) AS order_count FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.user_level,o.user_id) SELECT user_level,ROUND(SUM(order_count>=2)/COUNT(*),4) AS repeat_rate FROM user_orders GROUP BY user_level",
            ["users", "orders"],
            spoken=f"近{days}天各用户等级的复购率怎么样？买过两次以上的人除以买过的人。" if index < 2 else None,
        )
    arppu_windows = [54, 90, 126, 174, 246, 330]
    for days in arppu_windows:
        add(
            "refund_customer_product", "hard",
            f"最近{days}天按城市计算每位付费用户平均消费金额，返回城市、销售额、付费用户数和该指标，金额保留2位。",
            f"SELECT u.city,ROUND(SUM(o.paid_amount),2) AS sales_amount,COUNT(DISTINCT o.user_id) AS paying_users,ROUND(SUM(o.paid_amount)/COUNT(DISTINCT o.user_id),2) AS arppu FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.city",
            ["users", "orders"],
        )

    comparison_windows = [52, 84, 128, 176, 244, 320]
    for index, days in enumerate(comparison_windows):
        add(
            "complex", "hard",
            f"最近{days}天消费总额高于同用户等级平均值的用户有哪些？返回用户等级、用户名称和消费总额，按用户等级、消费总额降序和用户ID升序。",
            f"WITH customer_sales AS (SELECT u.user_id,u.user_name,u.user_level,SUM(o.paid_amount) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.user_id,u.user_name,u.user_level),level_avg AS (SELECT user_level,AVG(sales_amount) AS average_sales FROM customer_sales GROUP BY user_level) SELECT c.user_level,c.user_name,ROUND(c.sales_amount,2) AS sales_amount FROM customer_sales c JOIN level_avg a ON c.user_level=a.user_level WHERE c.sales_amount>a.average_sales ORDER BY c.user_level,c.sales_amount DESC,c.user_id ASC LIMIT 200",
            ["users", "orders"],
            spoken=f"近{days}天各等级里消费超过本等级平均线的用户都有谁？按等级和消费额排。" if index == 0 else None,
            ordered=True,
        )
    refund_ratio_specs = [(68, 0.10), (102, 0.15), (154, 0.20), (206, 0.25), (278, 0.30), (362, 0.35)]
    for index, (days, ratio) in enumerate(refund_ratio_specs):
        add(
            "complex", "hard",
            f"最近{days}天有效订单中，approved退款总额不超过订单实付金额{int(ratio*100)}%且至少有一笔approved退款的订单有哪些？返回订单ID、实付金额和退款金额，按订单ID升序，最多200条。",
            f"SELECT o.order_id,o.paid_amount,ROUND(SUM(r.refund_amount),2) AS refund_amount FROM orders o JOIN refunds r ON o.order_id=r.order_id AND r.refund_status='approved' WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY o.order_id,o.paid_amount HAVING SUM(r.refund_amount)<=o.paid_amount*{ratio} ORDER BY o.order_id ASC LIMIT 200",
            ["orders", "refunds"],
            spoken=f"近{days}天有通过退款但退款没超过实付{int(ratio*100)}%的成交单有哪些？按订单ID列。" if index == 0 else None,
            ordered=True,
        )

    random.Random(SEED).shuffle(cases)
    for index, case in enumerate(cases, 1):
        case["id"] = f"final_holdout_v2_{index:03}"
    return cases


def freeze() -> None:
    from app.tools.database import fetch_all

    if CASE_PATH.exists() or MANIFEST_PATH.exists():
        raise RuntimeError("Final Holdout v2 already exists; refusing to overwrite")
    cases = build_cases()
    previous_paths = [ROOT / "eval/daily_business_cases.json", ROOT / "eval/final_holdout_cases.json"]
    previous_questions = set()
    for path in previous_paths:
        previous_questions.update(case["question"] for case in json.loads(path.read_text()))
    assert len(cases) == 250
    assert len({case["question"] for case in cases}) == 250
    assert not ({case["question"] for case in cases} & previous_questions)
    assert Counter(case["difficulty"] for case in cases) == Counter({"easy": 125, "medium": 100, "hard": 25})
    assert Counter(case["category"] for case in cases) == Counter(
        {"filtering_aggregation": 75, "top_k_ranking": 50, "time_trend": 50,
         "one_two_table_join": 38, "refund_customer_product": 25, "complex": 12}
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
            "status": "FINAL HOLDOUT V2 FROZEN",
            "seed": SEED,
            "case_count": 250,
            "cases_sha256": digest(cases),
            "database": before,
            "reference_date": REFERENCE_DATE,
            "difficulty_counts": dict(Counter(case["difficulty"] for case in cases)),
            "category_counts": dict(Counter(case["category"] for case in cases)),
            "paraphrase_count": 30,
            "empty_result_count": sum(not case["ground_truth_result"] for case in cases),
            "scoring": "Frozen Daily Business strict comparator: exact rows/columns, numeric abs_tol 0.005, ordered cases enforce order.",
        },
    )
    print(json.dumps({"cases": 250, "paraphrase": 30, "sha256": digest(cases)}))


if __name__ == "__main__":
    freeze()
