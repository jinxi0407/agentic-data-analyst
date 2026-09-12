"""Canonical business definitions for e-commerce analytics SQL generation."""

from __future__ import annotations


VALID_ORDER_STATUSES = ("paid", "completed", "shipped")
APPROVED_REFUND_STATUS = "approved"
REFERENCE_DATE_PATTERN = "以 YYYY-MM-DD 为今天"


BUSINESS_METRIC_DICTIONARY = """
Business Metric Dictionary:
- 有效订单 / 真实销售 / 成交订单: orders.order_status IN ('paid','completed','shipped').
- 销售额 / 订单总金额 / 成交额:
  - order/customer/city/province/payment/status level: ROUND(SUM(orders.paid_amount), 2).
  - product/category/brand level: ROUND(SUM(order_items.item_amount), 2), joined through orders and products.
- 实付金额: orders.paid_amount at order level; order_items.item_amount at product-line level.
- 销量 / 购买数量 / 卖出件数: SUM(order_items.quantity), not COUNT(order_id).
- 客单价 / 平均订单金额: ROUND(AVG(orders.paid_amount), 2) for valid orders.
- 付费用户: COUNT(DISTINCT orders.user_id) where orders.order_status IN ('paid','completed','shipped').
- 每位付费用户平均消费金额 / ARPPU: ROUND(SUM(orders.paid_amount) / COUNT(DISTINCT orders.user_id), 2).
- 退款金额: ROUND(SUM(refunds.refund_amount), 2); actual refund money usually requires refunds.refund_status = 'approved'.
- 退款率: for product/category refund severity use
  ROUND(COALESCE(SUM(approved refund amount),0) / NULLIF(SUM(sales amount),0), 4).
- 退款通过率: ROUND(SUM(refund_status='approved') / COUNT(*), 4).
- 折扣金额 / 优惠金额: order-level uses orders.discount_amount; product/category level uses order_items.discount_amount.
- 在售商品: products.is_active = 1.
- 滞销商品: products LEFT JOIN order_items, SUM(quantity) ascending, include products with zero sales.
"""


TIME_SEMANTICS = """
Time Semantics:
- If the question contains "以 YYYY-MM-DD 为今天", that date is the only reference date. Never use the real system date for that question.
- For this benchmark the reference date is normally 2026-09-12.
- 最近7天 / 最近30天 / 最近90天: date_column >= DATE_SUB(reference_date, INTERVAL N DAY).
- 最近3个月 / 最近三个月 / 最近一季度: date_column >= DATE_SUB(reference_date, INTERVAL 3 MONTH).
- 最近半年 / 过去半年 / 过去六个月 / 这半年: date_column >= DATE_SUB(reference_date, INTERVAL 6 MONTH).
- 最近一年 / 过去一年: date_column >= DATE_SUB(reference_date, INTERVAL 12 MONTH).
- 本月: date_column >= first day of reference month AND date_column < first day of next month.
- 上月: previous complete natural month.
- 最近三个完整自然月: with reference date 2026-09-12, use >= '2026-06-01' AND < '2026-09-01'.
- 季度: use fixed quarter boundaries when year/quarter is explicit, e.g. 2026 Q2 is >= '2026-04-01' AND < '2026-07-01'.
- 年度 / 同比: compare full calendar years unless the question says year-to-date.
- 环比: aggregate by month with DATE_FORMAT(date_column,'%Y-%m') and ORDER BY month ASC.
- Sales/order time filters use orders.order_date. Refund time filters use refunds.refund_date.
"""


JOIN_RELATIONSHIPS = """
Foreign Key / Join Relationships:
- users.user_id = orders.user_id
- orders.order_id = order_items.order_id
- order_items.product_id = products.product_id
- orders.order_id = refunds.order_id
- order_items.order_item_id = refunds.order_item_id
- products.product_id = refunds.product_id

Preferred join paths:
- Customer/city/province sales: users -> orders.
- Product/category/brand sales or quantity: orders -> order_items -> products.
- Product/category refund amount or refund rate: refunds -> products, and for sales denominator use orders -> order_items -> products.
- User-level refunds: users -> orders -> refunds.
"""


TOP_K_RANKING_RULES = """
Top-K / Ranking Semantics:
- Always identify ranking metric, sort direction, and LIMIT before writing SQL.
- "最高 / 最多 / top / 排名前十" means ORDER BY the requested metric DESC.
- "最低 / 最少 / 滞销" means ORDER BY the requested metric ASC.
- 销售额最高 / 花钱最多 / 消费金额最高: rank by sales amount, not order count.
- 销量最高 / 购买数量最多 / 卖得最多: rank by SUM(order_items.quantity).
- 退款金额最高 / 退得多: rank by SUM(refunds.refund_amount) with approved refunds when asking actual refunds.
- 退款率最高 / 退货严重 / 老被退: rank by refund_rate DESC, then refund_amount DESC.
- If the question asks 商品, return products.product_name. 品类 returns products.category. 品牌 returns products.brand. 客户 returns users.user_name.
"""


PARAPHRASE_NORMALIZATION = """
Common Chinese Paraphrases:
- 退货 / 被退 / 老被退 / 退得多 / 退货严重 => refund analysis, usually approved refund amount or refund_rate.
- 卖得最好 / 卖得最多 / 购买最多 => quantity ranking unless the question explicitly says 销售额/金额.
- 比较能打 / 贡献大 => sales amount ranking or grouped sales.
- 大客户 / 花钱最多 / 消费最高 => customers ranked by SUM(orders.paid_amount).
- 老客户 / 高频客户 => customer/user analysis; use orders and users, not refunds alone.
- 最近一季度 => recent 3 months unless an explicit calendar quarter is given.
"""


CATEGORY_VALUES = """
Known exact product category values:
- 手机数码
- 家用电器
- 美妆个护
- 服饰鞋包
- 食品生鲜

Use exact category names from the question. Do not shorten 手机数码 to 手机 or 食品生鲜 to 食品.
"""


def business_context_text() -> str:
    return "\n\n".join(
        [
            BUSINESS_METRIC_DICTIONARY.strip(),
            TIME_SEMANTICS.strip(),
            JOIN_RELATIONSHIPS.strip(),
            TOP_K_RANKING_RULES.strip(),
            PARAPHRASE_NORMALIZATION.strip(),
            CATEGORY_VALUES.strip(),
        ]
    )
