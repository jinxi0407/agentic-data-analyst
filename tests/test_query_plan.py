from app.agent.query_plan import build_query_plan


def test_query_plan_refund_rate_product():
    plan = build_query_plan("以 2026-09-12 为今天，最近三个月退款率最高的5个商品有哪些？")

    assert plan["reference_date"] == "2026-09-12"
    assert plan["metric"] == "refund_rate"
    assert plan["limit"] == 5
    assert plan["ranking"] == {"metric": "refund_rate", "direction": "DESC"}
    assert {"orders", "order_items", "products", "refunds"}.issubset(set(plan["required_tables"]))


def test_query_plan_does_not_treat_dates_as_limit():
    plan = build_query_plan("以 2026-09-12 为今天，最近90天订单数是多少？")

    assert plan["metric"] == "order_count"
    assert plan["limit"] is None
    assert plan["time_range"]["sql"] == ">= DATE_SUB('2026-09-12', INTERVAL 90 DAY)"


def test_query_plan_exact_category_filter():
    plan = build_query_plan("以 2026-09-12 为今天，手机数码品类在售商品数量是多少？")

    assert plan["metric"] == "active_product_count"
    assert "products.category = '手机数码'" in plan["filters"]
    assert "active_products" in plan["filters"]
