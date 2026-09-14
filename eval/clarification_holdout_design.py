"""Independent holdout design written after gate freeze 2af21fc. Never used for tuning."""

from datetime import date, timedelta


def holdout_fixtures():
    cases = []
    valid = "o.order_status IN ('paid','completed','shipped')"
    categories = ["食品生鲜", "运动户外", "美妆个护", "母婴用品", "服饰鞋包"]
    cities = ["上海", "北京", "广州", "深圳", "杭州"]
    for i, (category, city) in enumerate(zip(categories, cities)):
        days = [19, 37, 53, 71, 89][i]
        start = (date(2026, 9, 12) - timedelta(days=days)).isoformat()
        threshold = 850 + i * 430
        minimum = 120 + i * 80
        top = 4 + i
        window = f"o.order_date >= '{start}' AND o.order_date < '2026-09-12'"
        families = [
            ("time", f"{city}最近{days}天新增注册客户有多少人？不含今天，只返回人数。",
             f"{city}最近新注册了多少客户？只返回人数。", f"最近{days}天，不含今天。",
             f"SELECT COUNT(*) AS total FROM users WHERE city='{city}' AND register_date>='{start}' AND register_date<'2026-09-12'"),
            ("metric", f"{category}累计销售额是多少？使用有效订单商品行实付金额，只返回金额。",
             f"汇总一下{category}的累计销售表现，只需要一个数字。", "我要有效订单商品行实付销售金额，汇总全部历史。",
             f"SELECT ROUND(SUM(i.item_amount),2) AS amount FROM order_items i JOIN orders o ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {valid} AND p.category='{category}'"),
            ("business_definition", f"{city}客户的有效订单中，实付金额超过{threshold}元的有几笔？只返回笔数。",
             f"{city}客户的有效订单里有多少大额订单？只返回笔数。", f"大额按单笔实付金额超过{threshold}元定义，全部历史。",
             f"SELECT COUNT(*) AS total FROM orders o JOIN users u ON u.user_id=o.user_id WHERE {valid} AND u.city='{city}' AND o.paid_amount>{threshold}"),
            ("filter", f"{category}在售商品中，标价低于{minimum}元的有几个？只返回数量。",
             f"{category}在售商品里便宜的有几个？只返回数量。", f"便宜指商品标价低于{minimum}元。",
             f"SELECT COUNT(*) AS total FROM products WHERE category='{category}' AND is_active=1 AND list_price<{minimum}"),
            ("metric", f"{city}客户按有效订单数量从高到低取前{top}名，返回用户ID和订单数；相同数量按用户ID升序。",
             f"找出{city}表现最好的前{top}名客户，返回用户ID和表现指标，指标相同按用户ID升序。",
             "表现按全部历史有效订单笔数衡量，从高到低排名。",
             f"SELECT u.user_id,COUNT(*) AS total FROM users u JOIN orders o ON o.user_id=u.user_id WHERE u.city='{city}' AND {valid} GROUP BY u.user_id ORDER BY total DESC,u.user_id ASC LIMIT {top}"),
            ("time", f"{category}在{start}到2026-09-11期间的已批准退款金额是多少？包含首尾日期，只返回金额。",
             f"{category}近期批准了多少退款金额？只返回金额。", f"退款日期从{start}到2026-09-11，包含首尾日期。",
             f"SELECT ROUND(SUM(r.refund_amount),2) AS amount FROM refunds r JOIN products p ON r.product_id=p.product_id WHERE p.category='{category}' AND r.refund_status='approved' AND r.refund_date>='{start}' AND r.refund_date<'2026-09-12'"),
            ("entity", f"统计{city}客户的累计有效订单实付金额，只返回总金额。",
             ["统计华东地区客户的累计有效订单实付金额，只返回总金额。",
              "统计北方地区客户的累计有效订单实付金额，只返回总金额。",
              "统计华南地区客户的累计有效订单实付金额，只返回总金额。",
              "统计珠三角地区客户的累计有效订单实付金额，只返回总金额。",
              "统计长三角地区客户的累计有效订单实付金额，只返回总金额。"][i],
             f"这次报表只统计客户城市为{city}的记录，不包含其他城市。",
             f"SELECT ROUND(SUM(o.paid_amount),2) AS amount FROM orders o JOIN users u ON o.user_id=u.user_id WHERE u.city='{city}' AND {valid}"),
            ("business_definition", f"{category}中2026-08-01及以后上架的在售商品有多少个？只返回数量。",
             f"{category}目前在售的新品有多少个？只返回数量。", "新品指2026-08-01及以后上架的商品。",
             f"SELECT COUNT(*) AS total FROM products WHERE category='{category}' AND is_active=1 AND launch_date>='2026-08-01'"),
            ("filter", f"{city}已注册客户中VIP有多少人？只返回人数。",
             f"{city}需要优先维护的客户有多少人？只返回人数。", "优先维护的客户是is_vip=1的VIP，不加其他条件。",
             f"SELECT COUNT(*) AS total FROM users WHERE city='{city}' AND is_vip=1"),
            ("multiple", f"{category}最近{days}天（不含今天）的有效订单销量是多少？只返回件数。",
             f"{category}最近卖得怎么样？只要一个汇总值。", f"统计最近{days}天、不含今天的有效订单销售数量，单位是件。",
             f"SELECT SUM(i.quantity) AS quantity FROM order_items i JOIN orders o ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {valid} AND p.category='{category}' AND {window}"),
            ("metric", f"{city}所有历史有效订单的订单数是多少？只返回笔数。",
             f"给我{city}的有效订单规模，只返回一个总计数字。", "规模指有效订单笔数，全部历史，不是金额或客户数。",
             f"SELECT COUNT(*) AS total FROM orders o JOIN users u ON u.user_id=o.user_id WHERE {valid} AND u.city='{city}'"),
            ("time", f"2026年第二季度{category}有效订单销售额是多少？按商品行实付金额统计，只返回总额。",
             f"帮我查下{category}那段时间的有效订单销售额，只返回总额。", "那段时间指2026年第二季度，即4月1日到6月30日。",
             f"SELECT ROUND(SUM(i.item_amount),2) AS total FROM order_items i JOIN orders o ON o.order_id=i.order_id JOIN products p ON p.product_id=i.product_id WHERE {valid} AND p.category='{category}' AND o.order_date>='2026-04-01' AND o.order_date<'2026-07-01'"),
        ]
        for family, (kind, clear, ambiguous, answer, sql) in enumerate(families):
            for needs, question in [(False, clear), (True, ambiguous)]:
                cases.append(dict(id=f"holdout-{i}-{family}-{'a' if needs else 'c'}",
                    question=question, should_clarify=needs, ambiguity_type=kind if needs else "none",
                    clarification_answer=answer if needs else None, resolved_question=clear,
                    reference_sql=sql, ordered="ORDER BY" in sql, family=family, ground_truth_result=[]))
    assert len(cases)==120 and len({case["question"] for case in cases})==120
    return cases
