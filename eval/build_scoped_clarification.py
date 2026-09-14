"""Create a fixed, self-authored scoped set; never imports candidate Gate code."""

import hashlib
import json
from pathlib import Path
import subprocess

from app.config import settings
from app.tools.database import fetch_all
from app.tools.guardrail import validate_and_rewrite_sql
from eval.scoring import compare, fingerprint, write_json

ROOT = Path(__file__).resolve().parents[1]
VALID = "o.order_status IN ('paid','completed','shipped')"
APPROVED = "r.refund_status='approved'"
UO = "users u JOIN orders o ON u.user_id=o.user_id"
ITEMS = "order_items i JOIN orders o ON i.order_id=o.order_id JOIN products p ON i.product_id=p.product_id"
RP = "refunds r JOIN products p ON r.product_id=p.product_id"


def generate():
    rows = []

    def add(family, question, sql, slot=None, answer=None, alternative=None, ordered=False):
        rows.append({"id": f"scoped-{len(rows)+1:03d}", "family": family, "question": question,
                     "should_clarify": slot is not None, "missing_slot": slot,
                     "persona_answer": answer, "reference_sql": sql,
                     "alternative_reference_sql": alternative, "ordered": ordered})

    # New intent families: payment channel, customer tier, discount, refund reasons and catalog stock.
    for k, (category, level, city) in enumerate([
        ("家用电器", "gold", "南京"), ("手机数码", "silver", "武汉"), ("美妆个护", "black", "西安")
    ]):
        specs = [
            ("channel_discount", "按支付方式汇总全部历史有效订单的优惠总额，返回支付方式和金额。",
             f"SELECT o.payment_method,ROUND(SUM(o.discount_amount),2) total FROM orders o WHERE {VALID} GROUP BY o.payment_method"),
            ("tier_spending", f"{level}等级客户的全部历史有效订单销售额是多少？只要金额。",
             f"SELECT ROUND(SUM(o.paid_amount),2) total FROM {UO} WHERE {VALID} AND u.user_level='{level}'"),
            ("brand_catalog", f"{category}里每个品牌有多少款商品？包含上下架商品，返回品牌和款数。",
             f"SELECT brand,COUNT(*) n FROM products WHERE category='{category}' GROUP BY brand"),
            ("catalog_avg_price", f"帮我算一下{category}在售商品的平均标价，只要金额，保留两位小数。",
             f"SELECT ROUND(AVG(list_price),2) value FROM products WHERE category='{category}' AND is_active=1"),
            ("city_payment", f"{city}客户用微信支付的全部历史有效订单有几笔？只要笔数。",
             f"SELECT COUNT(*) n FROM {UO} WHERE {VALID} AND u.city='{city}市' AND o.payment_method='wechat'"),
            ("refund_reason_count", "已批准退款按退款原因分组，每种原因有几条退款记录？全部历史，返回原因和条数。",
             "SELECT refund_reason,COUNT(*) n FROM refunds WHERE refund_status='approved' GROUP BY refund_reason"),
            ("channel_top", f"全部历史有效订单销售额最高的前{2+k}种支付方式是什么？返回支付方式和销售额，同额按支付方式升序。",
             f"SELECT o.payment_method,ROUND(SUM(o.paid_amount),2) total FROM orders o WHERE {VALID} GROUP BY o.payment_method ORDER BY total DESC,o.payment_method ASC LIMIT {2+k}"),
            ("brand_price_top", f"{category}标价最高的前{3+k}款商品，返回商品ID和标价，同价按商品ID升序。包含上下架商品。",
             f"SELECT product_id,list_price FROM products WHERE category='{category}' ORDER BY list_price DESC,product_id ASC LIMIT {3+k}"),
            ("month_channel", f"2026年{5+k}月每种支付方式的有效订单笔数，返回支付方式和笔数。",
             f"SELECT o.payment_method,COUNT(*) n FROM orders o WHERE {VALID} AND o.order_date>='2026-{5+k:02d}-01' AND o.order_date<'2026-{6+k:02d}-01' GROUP BY o.payment_method"),
            ("reason_amount", f"{category}因质量问题产生的已批准退款总金额是多少？全部历史，只返回金额。",
             f"SELECT ROUND(SUM(r.refund_amount),2) total FROM {RP} WHERE {APPROVED} AND r.refund_reason='质量问题' AND p.category='{category}'"),
            ("vip_channel_buyers", "全部历史中使用银行卡支付过有效订单的VIP客户一共有多少人？去重，只返回人数。",
             f"SELECT COUNT(DISTINCT u.user_id) n FROM {UO} WHERE {VALID} AND u.is_vip=1 AND o.payment_method='card'"),
            ("tier_order_mean", f"{level}等级客户的有效订单客单价是多少？全部历史，只要金额。",
             f"SELECT ROUND(SUM(o.paid_amount)/COUNT(*),2) total FROM {UO} WHERE {VALID} AND u.user_level='{level}'"),
            ("catalog_inactive", f"统计{category}已经下架的商品款数，只返回数量。",
             f"SELECT COUNT(*) n FROM products WHERE category='{category}' AND is_active=0"),
            ("zero_catalog", f"{category}商品里标价小于0元的有多少款？只要数量。",
             f"SELECT COUNT(*) n FROM products WHERE category='{category}' AND list_price<0"),
            ("absent_city", "拉萨客户中各等级分别有多少人？只返回等级和人数。没有记录也正常。",
             "SELECT user_level,COUNT(*) n FROM users WHERE city='拉萨' GROUP BY user_level"),
            ("order_day", f"2026年08月{10+k:02d}日各支付方式的有效订单销售额，返回支付方式和金额。",
             f"SELECT o.payment_method,ROUND(SUM(o.paid_amount),2) total FROM orders o WHERE {VALID} AND o.order_date='2026-08-{10+k:02d}' GROUP BY o.payment_method"),
            ("refund_reason_rank", f"按已批准退款金额从高到低列出前{2+k}个退款原因及金额，同额按原因升序。全部历史。",
             f"SELECT refund_reason,ROUND(SUM(refund_amount),2) total FROM refunds WHERE refund_status='approved' GROUP BY refund_reason ORDER BY total DESC,refund_reason ASC LIMIT {2+k}"),
            ("monthly_refund_count", "列出2026年第一季度每月已批准退款记录数，返回月份YYYY-MM和条数，按月份升序。",
             "SELECT DATE_FORMAT(refund_date,'%Y-%m') month,COUNT(*) n FROM refunds WHERE refund_status='approved' AND refund_date>='2026-01-01' AND refund_date<'2026-04-01' GROUP BY month ORDER BY month"),
            ("category_channel_qty", f"{category}全部历史有效订单按支付方式分别卖了多少件？返回支付方式和销量。",
             f"SELECT o.payment_method,SUM(i.quantity) n FROM {ITEMS} WHERE {VALID} AND p.category='{category}' GROUP BY o.payment_method"),
            ("city_tier_share", f"{city}每个客户等级的VIP人数分别是多少？只统计VIP，返回等级和人数。",
             f"SELECT user_level,COUNT(*) n FROM users WHERE city='{city}市' AND is_vip=1 GROUP BY user_level"),
        ]
        for family, q, sql in specs:
            # Repeated exact natural questions are made distinct through genuine declared filters.
            if k and family in {"channel_discount", "refund_reason_count", "vip_channel_buyers", "absent_city", "monthly_refund_count"}:
                if family == "channel_discount":
                    q=f"2026年{4+k}月按支付方式统计有效订单优惠总额，返回支付方式和金额。"
                    sql=sql.replace(" GROUP BY", f" AND o.order_date>='2026-{4+k:02d}-01' AND o.order_date<'2026-{5+k:02d}-01' GROUP BY")
                elif family == "refund_reason_count":
                    status = "pending" if k == 1 else "rejected"
                    q=f"全部历史退款状态为{status}的记录，按原因统计条数，返回原因和条数。"
                    sql=sql.replace("approved",status)
                elif family == "vip_channel_buyers":
                    method="cash" if k==1 else "alipay"
                    q=f"全部历史中以{method}支付过有效订单的VIP客户一共有多少人？只要去重人数。"
                    sql=sql.replace("card",method)
                elif family == "absent_city":
                    place="厦门" if k==1 else "青岛"
                    q=f"{place}客户各等级分别有多少人？只返回等级和人数。"
                    sql=sql.replace("拉萨",place)
                else:
                    q=f"列出2026年第{k+1}季度每月已批准退款记录数，返回月份YYYY-MM和条数，按月份升序。"
                    sql=("SELECT DATE_FORMAT(refund_date,'%Y-%m') month,COUNT(*) n FROM refunds "
                         f"WHERE refund_status='approved' AND refund_date>='2026-{1+3*k:02d}-01' "
                         f"AND refund_date<'2026-{4+3*k:02d}-01' GROUP BY month ORDER BY month")
            add(family,q,sql,ordered="ORDER BY" in sql)

    time_specs = [
        ("channel_period_count", "报表这段时间里，每种支付方式的有效订单有几笔？返回支付方式和笔数。", "o.order_date", f"SELECT o.payment_method,COUNT(*) n FROM orders o WHERE {VALID} AND {{time}} GROUP BY o.payment_method"),
        ("period_discount", "活动期间有效订单总共优惠了多少元？只要总额。", "o.order_date", f"SELECT ROUND(SUM(o.discount_amount),2) n FROM orders o WHERE {VALID} AND {{time}}"),
        ("period_aov", "近期有效订单客单价是多少？只要金额。", "o.order_date", f"SELECT ROUND(SUM(o.paid_amount)/COUNT(*),2) n FROM orders o WHERE {VALID} AND {{time}}"),
        ("period_vip_buyers", "这一期有多少VIP客户买过东西？按有效订单统计去重人数。", "o.order_date", f"SELECT COUNT(DISTINCT u.user_id) n FROM {UO} WHERE {VALID} AND u.is_vip=1 AND {{time}}"),
        ("period_channel_rank", "最近销售额最高的两种支付方式，返回支付方式和有效订单销售额，同额按支付方式升序。", "o.order_date", f"SELECT o.payment_method,ROUND(SUM(o.paid_amount),2) n FROM orders o WHERE {VALID} AND {{time}} GROUP BY o.payment_method ORDER BY n DESC,o.payment_method LIMIT 2"),
        ("period_city_groups", "活动期各城市贡献的有效订单销售额，返回城市和金额。", "o.order_date", f"SELECT u.city,ROUND(SUM(o.paid_amount),2) n FROM {UO} WHERE {VALID} AND {{time}} GROUP BY u.city"),
        ("period_reason_count", "近期因物流破损批准退款的记录有几条？只要条数。", "r.refund_date", f"SELECT COUNT(*) n FROM refunds r WHERE {APPROVED} AND r.refund_reason='物流破损' AND {{time}}"),
        ("period_reason_groups", "报表期按原因统计已批准退款金额，返回原因和金额。", "r.refund_date", f"SELECT r.refund_reason,ROUND(SUM(r.refund_amount),2) n FROM refunds r WHERE {APPROVED} AND {{time}} GROUP BY r.refund_reason"),
        ("period_card_amount", "近期银行卡支付的有效订单销售额是多少？只返回金额。", "o.order_date", f"SELECT ROUND(SUM(o.paid_amount),2) n FROM orders o WHERE {VALID} AND o.payment_method='card' AND {{time}}"),
        ("period_gold_discount", "这次活动期间gold客户的有效订单优惠总额是多少？只返回金额。", "o.order_date", f"SELECT ROUND(SUM(o.discount_amount),2) n FROM {UO} WHERE {VALID} AND u.user_level='gold' AND {{time}}"),
        ("period_silver_count", "这段统计时间里silver客户下了多少笔有效订单？只返回笔数。", "o.order_date", f"SELECT COUNT(*) n FROM {UO} WHERE {VALID} AND u.user_level='silver' AND {{time}}"),
        ("period_category_buyers", "近期购买手机数码的有效订单客户有多少人？去重，只返回人数。", "o.order_date", f"SELECT COUNT(DISTINCT o.user_id) n FROM {ITEMS} WHERE {VALID} AND p.category='手机数码' AND {{time}}"),
        ("period_category_qty", "促销那几天家用电器卖出了多少件？按有效订单销量统计，只要件数。", "o.order_date", f"SELECT SUM(i.quantity) n FROM {ITEMS} WHERE {VALID} AND p.category='家用电器' AND {{time}}"),
        ("period_top_customer_count", "近期下单最多的3位客户，按有效订单笔数排名，返回用户ID和笔数，同数按用户ID升序。", "o.order_date", f"SELECT o.user_id,COUNT(*) n FROM orders o WHERE {VALID} AND {{time}} GROUP BY o.user_id ORDER BY n DESC,o.user_id LIMIT 3"),
        ("period_cancel_count", "活动期取消的订单有多少笔？只返回笔数。", "o.order_date", "SELECT COUNT(*) n FROM orders o WHERE o.order_status='cancelled' AND {time}"),
        ("period_pending_refund", "最近新提交且状态仍为pending的退款申请有多少条？以refund_date为时间，只返回条数。", "r.refund_date", "SELECT COUNT(*) n FROM refunds r WHERE r.refund_status='pending' AND {time}"),
        ("period_reason_avg", "这段时间已批准的质量问题退款平均每条多少元？只返回金额。", "r.refund_date", f"SELECT ROUND(AVG(r.refund_amount),2) n FROM refunds r WHERE {APPROVED} AND r.refund_reason='质量问题' AND {{time}}"),
        ("period_tier_groups", "报表期内各客户等级的有效订单笔数，返回等级和笔数。", "o.order_date", f"SELECT u.user_level,COUNT(*) n FROM {UO} WHERE {VALID} AND {{time}} GROUP BY u.user_level"),
        ("period_new_vip", "那段招募期间注册的VIP一共有多少人？只返回人数。", "u.register_date", "SELECT COUNT(*) n FROM users u WHERE u.is_vip=1 AND {time}"),
        ("period_catalog", "活动期间上架的家用电器一共有多少款？包含现在下架的，只返回数量。", "p.launch_date", "SELECT COUNT(*) n FROM products p WHERE p.category='家用电器' AND {time}"),
    ]
    for j,(family,q,col,template) in enumerate(time_specs):
        year=2025 if j>=18 else 2026
        month=2+j%5
        start=f"{year}-{month:02d}-01";end=f"{year}-{month+1:02d}-01"
        nextend=f"{year}-{month+2:02d}-01"
        condition=f"{col}>='{start}' AND {col}<'{end}'"
        alt=f"{col}>='{start}' AND {col}<'{nextend}'"
        add(family,q,template.format(time=condition),"time",
            f"从{start}开始，包含当天，到{end}之前，不包含结束日。",
            template.format(time=alt),ordered="ORDER BY" in template)

    metric_specs = [
        ("channel_performance", "全部历史按支付方式展示成交表现，返回支付方式和一个指标值。", "o.payment_method", "orders o", VALID, "SUM(o.paid_amount)", "COUNT(*)", "用有效订单实付销售金额。"),
        ("tier_performance", "比较各客户等级的全部历史购买表现，返回等级和一个指标值。", "u.user_level", UO, VALID, "COUNT(*)", "SUM(o.paid_amount)", "用有效订单笔数。"),
        ("category_performance", "按商品类别汇总全部历史销售成绩，返回类别和一个指标值。", "p.category", ITEMS, VALID, "SUM(i.quantity)", "SUM(i.item_amount)", "用有效订单卖出的商品件数，也就是销量。"),
        ("reason_performance", "全部历史已批准退款按原因看规模，返回原因和一个指标值。", "r.refund_reason", "refunds r", APPROVED, "SUM(r.refund_amount)", "COUNT(*)", "用已批准退款金额。"),
        ("vip_performance", "VIP客户全部历史的有效订单成交表现是多少？只返回一个数。", None, UO, VALID+" AND u.is_vip=1", "SUM(o.paid_amount)", "COUNT(*)", "用有效订单销售金额。"),
        ("card_performance", "银行卡支付的全部历史有效订单，规模是多少？只返回一个数。", None, "orders o", VALID+" AND o.payment_method='card'", "COUNT(*)", "SUM(o.paid_amount)", "用有效订单笔数。"),
        ("wechat_customer", "微信渠道全部历史的客户成交情况给我一个汇总数。只考虑有效订单。", None, "orders o", VALID+" AND o.payment_method='wechat'", "COUNT(DISTINCT o.user_id)", "SUM(o.paid_amount)", "用去重的付费客户人数。"),
        ("gold_performance", "gold客户全部历史有效订单的消费水平给我一个数。", None, UO, VALID+" AND u.user_level='gold'", "AVG(o.paid_amount)", "SUM(o.paid_amount)", "用平均每笔有效订单的实付金额，即客单价。"),
        ("brand_performance", "家用电器各品牌全部历史销售表现，返回品牌和一个指标值。", "p.brand", ITEMS, VALID+" AND p.category='家用电器'", "SUM(i.item_amount)", "SUM(i.quantity)", "用有效订单商品行实付销售金额。"),
        ("reason_quality", "全部历史因质量问题批准的退款规模是多少？只返回一个数。", None, "refunds r", APPROVED+" AND r.refund_reason='质量问题'", "COUNT(*)", "SUM(r.refund_amount)", "用已批准退款记录条数。"),
        ("quarter_performance", "2026年第一季度的整体成交表现给我一个数，按有效订单统计。", None, "orders o", VALID+" AND o.order_date>='2026-01-01' AND o.order_date<'2026-04-01'", "SUM(o.paid_amount)", "COUNT(*)", "用销售金额。"),
        ("month_performance", "2026年8月各支付方式的交易表现，返回支付方式和一个指标值，只考虑有效订单。", "o.payment_method", "orders o", VALID+" AND o.order_date>='2026-08-01' AND o.order_date<'2026-09-01'", "COUNT(*)", "SUM(o.paid_amount)", "用有效订单笔数。"),
        ("tier_buying", "silver等级客户全部历史的购买活跃度给我一个数，只考虑有效订单。", None, UO, VALID+" AND u.user_level='silver'", "COUNT(DISTINCT u.user_id)", "COUNT(*)", "用有有效订单的去重客户人数。"),
        ("cash_performance", "现金支付渠道全部历史的成交指标是多少？只返回一个数，按有效订单统计。", None, "orders o", VALID+" AND o.payment_method='cash'", "SUM(o.paid_amount)", "COUNT(*)", "用有效订单销售金额。"),
        ("vip_channel_performance", "VIP客户各支付方式的全部历史交易表现，返回支付方式和一个指标值，只考虑有效订单。", "o.payment_method", UO, VALID+" AND u.is_vip=1", "COUNT(DISTINCT u.user_id)", "SUM(o.paid_amount)", "用每种支付方式下去重的付费客户人数。"),
        ("active_product_performance", "当前在售商品的全部历史销售规模是多少？只返回一个数，按有效订单统计。", None, ITEMS, VALID+" AND p.is_active=1", "SUM(i.quantity)", "SUM(i.item_amount)", "用售出的商品件数，即销量。"),
        ("inactive_product_performance", "当前下架商品过去累计销售表现是多少？只返回一个数，按有效订单统计。", None, ITEMS, VALID+" AND p.is_active=0", "SUM(i.item_amount)", "SUM(i.quantity)", "用商品行实付销售金额。"),
        ("refund_category_performance", "各商品类别全部历史已批准退款的规模，返回类别和一个指标值。", "p.category", RP, APPROVED, "COUNT(*)", "SUM(r.refund_amount)", "用已批准退款记录条数。"),
        ("nonvip_performance", "非VIP客户的全部历史有效订单消费情况给我一个汇总数。", None, UO, VALID+" AND u.is_vip=0", "AVG(o.paid_amount)", "SUM(o.paid_amount)", "用有效订单客单价，即平均每笔实付金额。"),
        ("refund_mean_performance", "已批准的七天无理由退款，全部历史退款水平给我一个汇总数。", None, "refunds r", APPROVED+" AND r.refund_reason='七天无理由'", "AVG(r.refund_amount)", "SUM(r.refund_amount)", "用每条已批准退款记录的平均退款金额。"),
    ]
    for family,q,dim,tables,where,metric,other,answer in metric_specs:
        def sql(m):
            value=f"ROUND({m},2)" if "amount" in m else m
            return f"SELECT {dim+',' if dim else ''}{value} n FROM {tables} WHERE {where}"+(f" GROUP BY {dim}" if dim else "")
        add(family,q,sql(metric),"metric",answer,sql(other))

    filter_specs = [
        ("selected_channel", "按我们这次选定的支付方式，统计全部历史有效订单笔数，只要笔数。", "orders o", VALID, "o.payment_method='alipay'", "o.payment_method='card'", "COUNT(*)", "支付方式是alipay，支付宝。"),
        ("selected_tier", "选定客户等级的全部历史有效订单销售额是多少？只返回金额。", UO, VALID, "u.user_level='gold'", "u.user_level='silver'", "ROUND(SUM(o.paid_amount),2)", "客户等级选gold。"),
        ("selected_refund_reason", "本次选定的退款原因，累计批准退款金额是多少？只要金额。", "refunds r", APPROVED, "r.refund_reason='描述不符'", "r.refund_reason='物流破损'", "ROUND(SUM(r.refund_amount),2)", "退款原因是描述不符。"),
        ("selected_province", "这次报表选定省份的客户总人数是多少？全部注册客户，只要人数。", "users u", "1=1", "u.province='湖北'", "u.province='江苏'", "COUNT(*)", "省份选择湖北。"),
        ("selected_city_set", "负责维护的那几座城市合计有多少VIP客户？只要人数。", "users u", "u.is_vip=1", "u.city IN ('南京市','武汉市')", "u.city IN ('北京市','成都市')", "COUNT(*)", "城市范围是南京和武汉这两座城市。"),
        ("selected_category", "本次关注的商品类别里，现在有多少款已经下架？只返回数量。", "products p", "p.is_active=0", "p.category='母婴用品'", "p.category='手机数码'", "COUNT(*)", "商品类别是母婴用品。"),
        ("price_floor", "在售商品中标价达到我们约定下限的有多少款？包含下限，只返回数量。", "products p", "p.is_active=1", "p.list_price>=600", "p.list_price>=1200", "COUNT(*)", "标价下限是600元，包含600元。"),
        ("discount_floor", "优惠金额超过本次指定门槛的有效订单有几笔？全部历史，只要笔数。", "orders o", VALID, "o.discount_amount>80", "o.discount_amount>160", "COUNT(*)", "优惠金额门槛为80元，严格大于80。"),
        ("refund_floor", "超过本次指定退款金额门槛的已批准退款有多少条？全部历史，只要条数。", "refunds r", APPROVED, "r.refund_amount>200", "r.refund_amount>500", "COUNT(*)", "退款金额门槛是200元，严格大于。"),
        ("chosen_vip", "按这次指定的VIP身份范围，统计全部历史有效订单销售额，只返回金额。", UO, VALID, "u.is_vip=0", "u.is_vip=1", "ROUND(SUM(o.paid_amount),2)", "只统计非VIP，is_vip=0。"),
        ("chosen_order_status", "指定订单状态的全部历史订单有多少笔？只返回笔数。", "orders o", "1=1", "o.order_status='unpaid'", "o.order_status='cancelled'", "COUNT(*)", "订单状态是unpaid，未支付。"),
        ("chosen_refund_status", "请数一下本次选定状态的退款记录，一共多少条？全部历史。", "refunds r", "1=1", "r.refund_status='rejected'", "r.refund_status='pending'", "COUNT(*)", "退款状态选rejected，已拒绝。"),
        ("catalog_price_cap", "手机数码中标价不超过选定预算上限的在售商品有多少款？只返回数量。", "products p", "p.category='手机数码' AND p.is_active=1", "p.list_price<=1800", "p.list_price<=3500", "COUNT(*)", "预算上限是1800元，含1800元。"),
        ("paid_band", "全部历史有效订单中，实付金额落在本次指定金额区间的有多少笔？只返回笔数。", "orders o", VALID, "o.paid_amount>=500 AND o.paid_amount<1500", "o.paid_amount>=1500 AND o.paid_amount<3000", "COUNT(*)", "实付金额至少500元且小于1500元。"),
        ("reason_category", "家用电器中，本次指定原因的已批准退款合计多少元？全部历史，只返回金额。", RP, APPROVED+" AND p.category='家用电器'", "r.refund_reason='七天无理由'", "r.refund_reason='质量问题'", "ROUND(SUM(r.refund_amount),2)", "原因指定七天无理由。"),
        ("selected_city_channels", "指定城市客户以微信支付的有效订单总笔数是多少？全部历史，只要笔数。", UO, VALID+" AND o.payment_method='wechat'", "u.city='成都市'", "u.city='北京市'", "COUNT(*)", "指定城市为成都。"),
        ("selected_two_tiers", "指定的两种客户等级合起来有多少注册用户？只要人数。", "users u", "1=1", "u.user_level IN ('silver','gold')", "u.user_level IN ('normal','black')", "COUNT(*)", "等级范围为silver和gold。"),
        ("selected_sale_state", "家用电器里按本次指定的上架状态统计商品数量，只返回款数。", "products p", "p.category='家用电器'", "p.is_active=0", "p.is_active=1", "COUNT(*)", "只要已下架商品，is_active=0。"),
        ("selected_order_channel_avg", "本次选定支付渠道的有效订单客单价是多少？全部历史，只返回金额。", "orders o", VALID, "o.payment_method='cash'", "o.payment_method='wechat'", "ROUND(AVG(o.paid_amount),2)", "支付渠道是cash，现金。"),
        ("selected_province_sales", "本次划定省份范围内客户的有效订单实付销售额总计多少？全部历史，只返回金额。", UO, VALID, "u.province IN ('江苏','浙江')", "u.province IN ('湖北','四川')", "ROUND(SUM(o.paid_amount),2)", "省份范围仅江苏和浙江。"),
    ]
    for family,q,tables,where,pred,alt,expr,answer in filter_specs:
        sql=lambda p: f"SELECT {expr} n FROM {tables} WHERE {where} AND {p}"
        add(family,q,sql(pred),"filter",answer,sql(alt))
    return rows


def main():
    target=ROOT/"eval/scoped_clarification_cases.json"
    if target.exists():
        raise SystemExit("Refusing to overwrite existing scoped set")
    cases=generate()
    assert len(cases)==120 and sum(c["should_clarify"] for c in cases)==60
    assert len({c["question"] for c in cases})==120
    old=[]
    for name in ["clarification_dev.json","clarification_holdout_corrected.json"]:
        old.extend(json.loads((ROOT/"eval"/name).read_text()))
    assert not ({c["question"] for c in cases}&{c["question"] for c in old})
    checks=[]
    for c in cases:
        guard=validate_and_rewrite_sql(c["reference_sql"])
        assert guard.ok, c["id"]
        c["ground_truth_result"]=fetch_all(c["reference_sql"])
        changed=None
        if c["alternative_reference_sql"]:
            alternative=fetch_all(c["alternative_reference_sql"])
            changed=not compare(c["ground_truth_result"],alternative,c["ordered"])
            c["alternative_ground_truth_result"]=alternative
        checks.append({"id":c["id"],"reference_executed":True,"alternative_result_differs":changed,
                       "row_count":len(c["ground_truth_result"]),"family":c["family"]})
    write_json(target,cases)
    write_json(ROOT/"eval/scoped_reference_validation.json",checks)
    paths=["app/agent/scoped_clarification.py","app/agent/entity_context.py","app/tools/qwen.py",
           "eval/strong_baseline_v2.py","eval/strong_baseline.py","eval/scoring.py",
           "eval/run_scoped_clarification.py","eval/SCOPED_CLARIFICATION_PROTOCOL.md",
           "eval/scoped_clarification_cases.json","eval/scoped_reference_validation.json",
           "eval/SCOPED_DATA_REVIEW.md"]
    freeze={"code_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "reference_date":"2026-09-12","timezone":"Asia/Shanghai","chat_model":settings.qwen_chat_model,
            "embedding_model":settings.qwen_embedding_model,"sql_temperature":0.05,"gate_temperature":0,
            "format":"json_schema_strict","execution_retry":2,"transport_retry":0,"workers":1,
            "database":fingerprint(fetch_all),
            "hashes":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    write_json(ROOT/"eval/scoped_clarification_freeze.json",freeze)
    print(json.dumps({"count":120,"clear":60,"ambiguous":60,"alternatives_result_differs":sum(x["alternative_result_differs"] is True for x in checks)}))


if __name__=="__main__": main()
