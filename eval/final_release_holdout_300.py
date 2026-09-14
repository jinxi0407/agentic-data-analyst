"""Generate and freeze the final 300-case release holdout."""

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
SEED = 20260916
VALID = "order_status IN ('paid','completed','shipped')"
CASE_PATH = ROOT / "eval/final_release_holdout_300_cases.json"
MANIFEST_PATH = ROOT / "eval/final_release_holdout_300_manifest.json"


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def add(category, difficulty, question, sql, tables, *, spoken=None, ordered=False):
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

    categories = ["家用电器", "手机数码", "服饰鞋包", "母婴用品", "美妆个护", "运动户外", "食品生鲜"]
    product_filters = [
        ("已下架商品数", "COUNT(*)", "is_active=0"),
        ("在售商品最高标价", "ROUND(MAX(list_price),2)", "is_active=1"),
        ("在售商品最低成本价", "ROUND(MIN(cost_price),2)", "is_active=1"),
        ("2026年上架的在售商品数", "COUNT(*)", "is_active=1 AND launch_date>='2026-01-01' AND launch_date<'2027-01-01'"),
        ("在售商品平均标价毛利率", "ROUND(AVG((list_price-cost_price)/NULLIF(list_price,0)),4)", "is_active=1"),
    ]
    for category_index, category in enumerate(categories):
        for metric_index, (label, expression, condition) in enumerate(product_filters):
            spoken = None
            if metric_index == 0:
                spoken = f"{category}里已经不卖的商品有多少款？"
            add(
                "filtering_aggregation", "easy", f"{category}的{label}是多少？",
                f"SELECT {expression} AS value FROM products WHERE category='{category}' AND {condition}",
                ["products"], spoken=spoken,
            )

    cities = ["北京市", "成都市", "武汉市", "广州市", "上海市", "杭州市", "南京市", "西安市"]
    user_filters = [
        ("黑卡用户数", "COUNT(*)", "user_level='black'"),
        ("普通等级VIP用户数", "COUNT(*)", "user_level='normal' AND is_vip=1"),
        ("2024年底前注册用户数", "COUNT(*)", "register_date<'2025-01-01'"),
        ("非VIP银卡用户数", "COUNT(*)", "user_level='silver' AND is_vip=0"),
        ("最近一次用户注册日期", "MAX(register_date)", "1=1"),
    ]
    for city_index, city in enumerate(cities):
        for metric_index, (label, expression, condition) in enumerate(user_filters):
            spoken = f"{city}黑卡会员一共有多少？" if metric_index == 0 and city_index < 5 else None
            add(
                "filtering_aggregation", "easy", f"{city}的{label}是多少？",
                f"SELECT {expression} AS value FROM users WHERE city='{city}' AND {condition}",
                ["users"], spoken=spoken,
            )

    order_filter_windows = [
        ("2026年1月", "2026-01-01", "2026-02-01", "wechat"),
        ("2026年2月", "2026-02-01", "2026-03-01", "alipay"),
        ("2026年3月", "2026-03-01", "2026-04-01", "card"),
        ("2026年4月", "2026-04-01", "2026-05-01", "cash"),
        ("2026年5月", "2026-05-01", "2026-06-01", "wechat"),
    ]
    order_filter_metrics = [
        ("订单总数", "COUNT(*)"),
        ("平均原始金额", "ROUND(AVG(gross_amount),2)"),
        ("优惠金额占原始金额比例", "ROUND(SUM(discount_amount)/NULLIF(SUM(gross_amount),0),4)"),
    ]
    for label, start, end, payment in order_filter_windows:
        for metric_label, expression in order_filter_metrics:
            add(
                "filtering_aggregation", "easy",
                f"{label}使用{payment}支付的{metric_label}是多少？包含所有订单状态。",
                f"SELECT {expression} AS value FROM orders WHERE payment_method='{payment}' AND order_date>='{start}' AND order_date<'{end}'",
                ["orders"],
            )

    brands = ["优选", "澜庭", "松果", "云栖", "北辰", "森活", "青橙", "星禾"]
    product_rankings = [
        (4, "list_price", "DESC", "标价最高", "product_name,list_price AS metric"),
        (5, "cost_price", "ASC", "成本价最低", "product_name,cost_price AS metric"),
        (6, "list_price-cost_price", "DESC", "单件标价毛利最大", "product_name,ROUND(list_price-cost_price,2) AS metric"),
        (3, "launch_date", "DESC", "最近上架", "product_name,launch_date AS metric"),
        (5, "list_price/NULLIF(cost_price,0)", "DESC", "标价成本倍数最高", "product_name,ROUND(list_price/NULLIF(cost_price,0),4) AS metric"),
    ]
    for brand in brands:
        for metric_index, (limit, expression, direction, label, select_expr) in enumerate(product_rankings):
            spoken = f"{brand}现在卖的商品里，最贵的{limit}款是什么？同价按商品ID排。" if metric_index == 0 else None
            add(
                "top_k_ranking", "easy",
                f"{brand}品牌在售商品中{label}的前{limit}种是什么？返回商品名称和指标，同值按商品ID升序。",
                f"SELECT {select_expr} FROM products WHERE brand='{brand}' AND is_active=1 ORDER BY {expression} {direction},product_id ASC LIMIT {limit}",
                ["products"], spoken=spoken, ordered=True,
            )

    ranking_windows = [33, 57, 81, 123, 189]
    joined_rankings = [
        (4, "u.province", "ROUND(SUM(o.paid_amount),2)", "销售额最高的省份"),
        (5, "u.city", "ROUND(AVG(o.paid_amount),2)", "平均订单实付最高的城市"),
        (6, "u.user_name", "ROUND(SUM(o.discount_amount),2)", "累计优惠最多的用户"),
        (3, "u.user_level", "COUNT(DISTINCT o.user_id)", "付费用户数最多的用户等级"),
    ]
    for days_index, days in enumerate(ranking_windows):
        for metric_index, (limit, dimension, expression, label) in enumerate(joined_rankings):
            group_id = "u.user_id,u.user_name" if dimension == "u.user_name" else dimension
            tie = "u.user_id" if dimension == "u.user_name" else dimension
            add(
                "top_k_ranking", "medium",
                f"最近{days}天{label}前{limit}名是什么？只统计有效订单，返回维度和指标，同值按维度升序。",
                f"SELECT {dimension} AS dimension,{expression} AS metric FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY {group_id} ORDER BY metric DESC,{tie} ASC LIMIT {limit}",
                ["users", "orders"], ordered=True,
            )

    explicit_periods = [
        ("2025年第四季度", "2025-10-01", "2026-01-01"),
        ("2026年1月上半月", "2026-01-01", "2026-01-16"),
        ("2026年1月下半月", "2026-01-16", "2026-02-01"),
        ("2026年2月", "2026-02-01", "2026-03-01"),
        ("2026年3月", "2026-03-01", "2026-04-01"),
        ("2026年4月", "2026-04-01", "2026-05-01"),
        ("2026年5月", "2026-05-01", "2026-06-01"),
        ("2026年6月", "2026-06-01", "2026-07-01"),
        ("2026年7月", "2026-07-01", "2026-08-01"),
        ("2026年8月", "2026-08-01", "2026-09-01"),
    ]
    period_metrics = [("有效订单销售额", "ROUND(SUM(paid_amount),2)"), ("付费用户数", "COUNT(DISTINCT user_id)")]
    for period_index, (label, start, end) in enumerate(explicit_periods):
        for metric_index, (metric_label, expression) in enumerate(period_metrics):
            spoken = f"{label}一共有多少成交额？" if metric_index == 0 and period_index < 7 else None
            add(
                "time_trend", "easy", f"{label}的{metric_label}是多少？",
                f"SELECT {expression} AS value FROM orders WHERE {VALID} AND order_date>='{start}' AND order_date<'{end}'",
                ["orders"], spoken=spoken,
            )

    weekly_windows = [42, 70, 98, 126, 168, 224, 280]
    weekly_metrics = [
        ("销售额", "ROUND(SUM(paid_amount),2)"),
        ("有效订单数", "COUNT(*)"),
        ("付费用户数", "COUNT(DISTINCT user_id)"),
        ("平均实付金额", "ROUND(AVG(paid_amount),2)"),
        ("优惠率", "ROUND(SUM(discount_amount)/NULLIF(SUM(gross_amount),0),4)"),
    ]
    for days in weekly_windows:
        for metric_label, expression in weekly_metrics:
            add(
                "time_trend", "medium",
                f"最近{days}天按自然周统计{metric_label}，只统计有效订单；返回周和指标，按周升序。",
                f"SELECT DATE_FORMAT(order_date,'%x-W%v') AS week,{expression} AS value FROM orders WHERE {VALID} AND order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY week ORDER BY week",
                ["orders"], ordered=True,
            )

    comparison_periods = [
        ("2026年1月与2025年12月", "2025-12-01", "2026-01-01", "2026-01-01", "2026-02-01"),
        ("2026年2月与1月", "2026-01-01", "2026-02-01", "2026-02-01", "2026-03-01"),
        ("2026年第二季度与第一季度", "2026-01-01", "2026-04-01", "2026-04-01", "2026-07-01"),
        ("2026年7月与6月", "2026-06-01", "2026-07-01", "2026-07-01", "2026-08-01"),
        ("2026年8月与7月", "2026-07-01", "2026-08-01", "2026-08-01", "2026-09-01"),
    ]
    for label, p_start, p_end, c_start, c_end in comparison_periods:
        add(
            "time_trend", "hard",
            f"分别统计{label}的有效订单销售额和订单数，并给出后一期间销售额相对前一期间的环比增长率。",
            "SELECT ROUND(previous_sales,2) AS previous_sales,ROUND(current_sales,2) AS current_sales,"
            "previous_orders,current_orders,ROUND((current_sales-previous_sales)/NULLIF(previous_sales,0),4) AS sales_growth_rate FROM ("
            f"SELECT SUM(CASE WHEN order_date>='{p_start}' AND order_date<'{p_end}' THEN paid_amount ELSE 0 END) AS previous_sales,"
            f"SUM(CASE WHEN order_date>='{c_start}' AND order_date<'{c_end}' THEN paid_amount ELSE 0 END) AS current_sales,"
            f"SUM(CASE WHEN order_date>='{p_start}' AND order_date<'{p_end}' THEN 1 ELSE 0 END) AS previous_orders,"
            f"SUM(CASE WHEN order_date>='{c_start}' AND order_date<'{c_end}' THEN 1 ELSE 0 END) AS current_orders "
            f"FROM orders WHERE {VALID} AND order_date>='{p_start}' AND order_date<'{c_end}') x",
            ["orders"],
        )

    join_windows = [24, 39, 63, 87, 111, 147, 183, 231, 303]
    for window_index, days in enumerate(join_windows):
        join_specs = [
            (
                "按用户等级和支付方式统计有效订单数与销售额",
                f"SELECT u.user_level,o.payment_method,COUNT(*) AS order_count,ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.user_level,o.payment_method",
                ["users", "orders"],
            ),
            (
                "按城市统计使用过的支付方式数和有效订单平均实付金额",
                f"SELECT u.city,COUNT(DISTINCT o.payment_method) AS payment_method_count,ROUND(AVG(o.paid_amount),2) AS average_paid FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.city",
                ["users", "orders"],
            ),
            (
                "按商品品类统计全部订单明细的数量、明细金额和平均成交单价",
                f"SELECT p.category,SUM(i.quantity) AS quantity,ROUND(SUM(i.item_amount),2) AS item_amount,ROUND(SUM(i.item_amount)/NULLIF(SUM(i.quantity),0),2) AS average_unit_paid FROM products p JOIN order_items i ON p.product_id=i.product_id WHERE i.created_at>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.category",
                ["products", "order_items"],
            ),
            (
                "按品牌统计approved退款笔数、退款金额和涉及商品数",
                f"SELECT p.brand,COUNT(*) AS refund_count,ROUND(SUM(r.refund_amount),2) AS refund_amount,COUNT(DISTINCT r.product_id) AS product_count FROM products p JOIN refunds r ON p.product_id=r.product_id WHERE r.refund_status='approved' AND r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.brand",
                ["products", "refunds"],
            ),
            (
                "按订单支付方式统计approved退款订单数和退款金额",
                f"SELECT o.payment_method,COUNT(DISTINCT o.order_id) AS refund_order_count,ROUND(SUM(r.refund_amount),2) AS refund_amount FROM orders o JOIN refunds r ON o.order_id=r.order_id WHERE r.refund_status='approved' AND r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY o.payment_method",
                ["orders", "refunds"],
            ),
        ]
        for spec_index, (description, sql, tables) in enumerate(join_specs):
            spoken = f"近{days}天各等级、各支付渠道成交了多少单和多少钱？" if spec_index == 0 and window_index < 4 else None
            add(
                "one_two_table_join", "medium", f"最近{days}天{description}。",
                sql, tables, spoken=spoken,
            )

    business_categories = ["家用电器", "手机数码", "服饰鞋包", "母婴用品", "美妆个护"]
    business_cities = ["武汉市", "杭州市", "西安市", "北京市", "成都市"]
    for index, (category, city) in enumerate(zip(business_categories, business_cities)):
        specs = [
            (
                f"最近180天{category}各退款原因的approved退款笔数和退款金额是多少？",
                f"SELECT r.refund_reason,COUNT(*) AS refund_count,ROUND(SUM(r.refund_amount),2) AS refund_amount FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE p.category='{category}' AND r.refund_status='approved' AND r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL 180 DAY) GROUP BY r.refund_reason",
                ["refunds", "products"],
            ),
            (
                f"{category}各品牌的商品数、在售商品数和在售率是多少？",
                f"SELECT brand,COUNT(*) AS product_count,SUM(is_active=1) AS active_count,ROUND(SUM(is_active=1)/COUNT(*),4) AS active_rate FROM products WHERE category='{category}' GROUP BY brand",
                ["products"],
            ),
            (
                f"最近120天{city}各用户等级的付费用户数、有效订单数和销售额是多少？",
                f"SELECT u.user_level,COUNT(DISTINCT o.user_id) AS paying_users,COUNT(*) AS order_count,ROUND(SUM(o.paid_amount),2) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE u.city='{city}' AND o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL 120 DAY) GROUP BY u.user_level",
                ["users", "orders"],
            ),
            (
                f"{city}各用户等级的用户数、VIP用户数和VIP占比是多少？",
                f"SELECT user_level,COUNT(*) AS user_count,SUM(is_vip=1) AS vip_count,ROUND(SUM(is_vip=1)/COUNT(*),4) AS vip_rate FROM users WHERE city='{city}' GROUP BY user_level",
                ["users"],
            ),
        ]
        for spec_index, (question, sql, tables) in enumerate(specs):
            spoken = f"近半年{category}通过的退款都是什么原因，各多少笔多少钱？" if spec_index == 0 and index < 3 else None
            add("refund_customer_product", "medium", question, sql, tables, spoken=spoken)

    hard_windows = [72, 108, 156, 216, 288]
    for days in hard_windows:
        add(
            "refund_customer_product", "hard",
            f"最近{days}天按商品品类分别统计有效订单明细销售额和approved退款金额；两个指标必须先独立聚合再连接。",
            f"WITH sales AS (SELECT i.product_id,SUM(i.item_amount) AS sales_amount FROM order_items i JOIN orders o ON i.order_id=o.order_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY i.product_id), refunds_agg AS (SELECT product_id,SUM(refund_amount) AS refund_amount FROM refunds WHERE refund_status='approved' AND refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY product_id), product_metrics AS (SELECT p.category,SUM(COALESCE(s.sales_amount,0)) AS sales_amount,SUM(COALESCE(r.refund_amount,0)) AS refund_amount FROM products p LEFT JOIN sales s ON p.product_id=s.product_id LEFT JOIN refunds_agg r ON p.product_id=r.product_id GROUP BY p.category) SELECT category,ROUND(sales_amount,2) AS sales_amount,ROUND(refund_amount,2) AS refund_amount FROM product_metrics",
            ["orders", "order_items", "products", "refunds"],
        )
        add(
            "refund_customer_product", "hard",
            f"最近{days}天按用户等级同时统计有效订单销售额、approved退款金额和净收入；订单与退款先按用户独立汇总。",
            f"WITH sales AS (SELECT user_id,SUM(paid_amount) AS sales_amount FROM orders WHERE {VALID} AND order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY user_id), refund_by_user AS (SELECT o.user_id,SUM(r.refund_amount) AS refund_amount FROM refunds r JOIN orders o ON r.order_id=o.order_id WHERE r.refund_status='approved' AND r.refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY o.user_id) SELECT u.user_level,ROUND(SUM(COALESCE(s.sales_amount,0)),2) AS sales_amount,ROUND(SUM(COALESCE(r.refund_amount,0)),2) AS refund_amount,ROUND(SUM(COALESCE(s.sales_amount,0))-SUM(COALESCE(r.refund_amount,0)),2) AS net_revenue FROM users u LEFT JOIN sales s ON u.user_id=s.user_id LEFT JOIN refund_by_user r ON u.user_id=r.user_id GROUP BY u.user_level",
            ["users", "orders", "refunds"],
        )

    complex_windows = [64, 96, 144, 208, 272]
    for index, days in enumerate(complex_windows):
        spoken = f"近{days}天每个品牌里成交额最高的商品是哪款？并列时按商品ID。" if index < 2 else None
        add(
            "complex", "hard",
            f"最近{days}天找出每个品牌中有效订单明细销售额最高的商品，返回品牌、商品名称和销售额；并列按商品ID升序。",
            f"WITH product_sales AS (SELECT p.brand,p.product_id,p.product_name,SUM(i.item_amount) AS sales_amount FROM products p JOIN order_items i ON p.product_id=i.product_id JOIN orders o ON i.order_id=o.order_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY p.brand,p.product_id,p.product_name), ranked AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY brand ORDER BY sales_amount DESC,product_id ASC) AS rn FROM product_sales) SELECT brand,product_name,ROUND(sales_amount,2) AS sales_amount FROM ranked WHERE rn=1 ORDER BY brand",
            ["products", "order_items", "orders"], spoken=spoken, ordered=True,
        )
        add(
            "complex", "hard",
            f"最近{days}天先汇总每位用户的有效订单消费，再找出消费高于所在省份用户平均值且至少有3笔订单的用户；返回省份、用户名称、订单数和消费额。",
            f"WITH customer_sales AS (SELECT u.province,u.user_id,u.user_name,COUNT(*) AS order_count,SUM(o.paid_amount) AS sales_amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY u.province,u.user_id,u.user_name), province_avg AS (SELECT province,AVG(sales_amount) AS avg_sales FROM customer_sales GROUP BY province) SELECT c.province,c.user_name,c.order_count,ROUND(c.sales_amount,2) AS sales_amount FROM customer_sales c JOIN province_avg a ON c.province=a.province WHERE c.sales_amount>a.avg_sales AND c.order_count>=3 ORDER BY c.province,c.sales_amount DESC,c.user_id ASC LIMIT 200",
            ["users", "orders"], ordered=True,
        )
        add(
            "complex", "hard",
            f"最近{days}天先按订单汇总approved退款，再找出退款率在10%到40%之间且approved退款不少于2笔的有效订单；返回订单ID、实付金额、退款金额和退款率。",
            f"WITH refund_by_order AS (SELECT order_id,COUNT(*) AS refund_count,SUM(refund_amount) AS refund_amount FROM refunds WHERE refund_status='approved' AND refund_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) GROUP BY order_id) SELECT o.order_id,o.paid_amount,ROUND(r.refund_amount,2) AS refund_amount,ROUND(r.refund_amount/NULLIF(o.paid_amount,0),4) AS refund_rate FROM orders o JOIN refund_by_order r ON o.order_id=r.order_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{REFERENCE_DATE}',INTERVAL {days} DAY) AND r.refund_count>=2 AND r.refund_amount/o.paid_amount BETWEEN 0.10 AND 0.40 ORDER BY o.order_id LIMIT 200",
            ["orders", "refunds"], ordered=True,
        )

    random.Random(SEED).shuffle(cases)
    for index, case in enumerate(cases, 1):
        case["id"] = f"final_release_300_{index:03}"
    return cases


def freeze() -> None:
    from app.tools.database import fetch_all

    if CASE_PATH.exists() or MANIFEST_PATH.exists():
        raise RuntimeError("Final Release Holdout 300 already exists; refusing to overwrite")
    cases = build_cases()
    previous_questions = set()
    for path in (ROOT / "eval").glob("*cases.json"):
        if path == CASE_PATH:
            continue
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            previous_questions.update(row.get("question") for row in payload if isinstance(row, dict))
    assert len(cases) == 300
    assert len({case["question"] for case in cases}) == 300
    assert not ({case["question"] for case in cases} & previous_questions)
    assert Counter(case["difficulty"] for case in cases) == Counter({"easy": 150, "medium": 120, "hard": 30})
    assert Counter(case["category"] for case in cases) == Counter(
        {"filtering_aggregation": 90, "top_k_ranking": 60, "time_trend": 60,
         "one_two_table_join": 45, "refund_customer_product": 30, "complex": 15}
    )
    assert sum(case["paraphrase"] for case in cases) == 36
    before = fingerprint(fetch_all)
    for case in cases:
        case["ground_truth_result"] = fetch_all(case["reference_sql"])
        assert len(case["ground_truth_result"]) <= 200
    assert before == fingerprint(fetch_all)
    write_json(CASE_PATH, cases)
    write_json(
        MANIFEST_PATH,
        {
            "status": "FINAL RELEASE HOLDOUT 300 FROZEN",
            "seed": SEED,
            "case_count": 300,
            "cases_sha256": digest(cases),
            "database": before,
            "reference_date": REFERENCE_DATE,
            "difficulty_counts": dict(Counter(case["difficulty"] for case in cases)),
            "category_counts": dict(Counter(case["category"] for case in cases)),
            "paraphrase_count": 36,
            "empty_result_count": sum(not case["ground_truth_result"] for case in cases),
            "scoring": "Frozen strict comparator: exact rows/columns, numeric abs_tol 0.005, ordered cases enforce order.",
        },
    )
    print(json.dumps({"cases": 300, "paraphrase": 36, "sha256": digest(cases)}))


if __name__ == "__main__":
    freeze()
