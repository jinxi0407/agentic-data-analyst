"""Lightweight deterministic query planning before SQL generation."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def build_query_plan(question: str, skill_name: str = "") -> Dict[str, Any]:
    text = question.lower()
    reference_date = _extract_reference_date(question)
    metric = _detect_metric(question)
    dimensions = _detect_dimensions(question)
    time_range = _detect_time_range(question, reference_date)
    ranking = _detect_ranking(question, metric)
    limit = _detect_limit(question)
    filters = _detect_filters(question, metric)
    required_tables = _required_tables(metric, dimensions, filters)
    normalized_terms = _normalize_terms(question)

    return {
        "reference_date": reference_date,
        "metric": metric,
        "dimensions": dimensions,
        "time_range": time_range,
        "filters": filters,
        "ranking": ranking,
        "limit": limit,
        "required_tables": required_tables,
        "normalized_terms": normalized_terms,
        "skill": skill_name,
        "notes": _plan_notes(metric, dimensions, text),
    }


def format_query_plan(plan: Dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2)


def _extract_reference_date(question: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s*为今天", question)
    return match.group(1) if match else "CURRENT_DATE"


def _detect_metric(question: str) -> str:
    if any(term in question for term in ["退款率", "退货严重", "老被退", "退得特别多"]):
        return "refund_rate"
    if any(term in question for term in ["退款通过率", "通过率"]):
        return "refund_approval_rate"
    if any(term in question for term in ["退款金额", "退款总额", "退得多", "退货"]):
        return "refund_amount"
    if any(term in question for term in ["销量", "购买数量", "卖得最多", "买最多", "最喜欢购买"]):
        return "quantity"
    if any(term in question for term in ["客单价", "平均订单金额"]):
        return "avg_order_amount"
    if any(term in question for term in ["每位付费用户平均消费", "arppu"]):
        return "arppu"
    if any(term in question for term in ["订单数", "订单量", "贡献了多少订单"]):
        return "order_count"
    if any(term in question for term in ["折扣金额", "优惠金额"]):
        return "discount_amount"
    if any(term in question for term in ["在售商品数量", "商品数量"]):
        return "active_product_count"
    if any(term in question for term in ["平均商品价格", "平均价格"]):
        return "avg_product_price"
    return "sales_amount"


def _detect_dimensions(question: str) -> List[str]:
    dimensions: List[str] = []
    mapping = [
        ("product", ["商品", "产品"]),
        ("category", ["品类"]),
        ("brand", ["品牌"]),
        ("customer", ["客户", "用户", "大客户"]),
        ("city", ["城市"]),
        ("province", ["省份"]),
        ("user_level", ["用户等级", "银卡", "金卡", "黑卡", "普通"]),
        ("payment_method", ["支付方式"]),
        ("order_status", ["订单状态"]),
        ("refund_reason", ["退款原因", "原因"]),
        ("month", ["每月", "月份", "月趋势", "环比"]),
        ("quarter", ["季度"]),
        ("is_vip", ["vip", "VIP"]),
    ]
    for dimension, terms in mapping:
        if any(term in question for term in terms):
            dimensions.append(dimension)
    if any(term in question for term in ["趋势", "每个月", "过去几个月", "这半年每个月"]):
        dimensions.append("month")
    return _dedupe(dimensions)


def _detect_time_range(question: str, reference_date: str) -> Dict[str, Any]:
    if "最近7天" in question:
        return {"kind": "relative", "column_hint": "orders.order_date", "sql": f">= DATE_SUB('{reference_date}', INTERVAL 7 DAY)"}
    if any(term in question for term in ["最近30天", "近30天"]):
        return {"kind": "relative", "column_hint": "orders.order_date", "sql": f">= DATE_SUB('{reference_date}', INTERVAL 30 DAY)"}
    if any(term in question for term in ["最近90天", "近90天"]):
        return {"kind": "relative", "column_hint": "orders.order_date/refunds.refund_date", "sql": f">= DATE_SUB('{reference_date}', INTERVAL 90 DAY)"}
    if any(term in question for term in ["最近三个月", "最近3个月", "最近一季度"]):
        return {"kind": "relative", "column_hint": "orders.order_date/refunds.refund_date", "sql": f">= DATE_SUB('{reference_date}', INTERVAL 3 MONTH)"}
    if any(term in question for term in ["最近半年", "过去半年", "过去六个月", "这半年"]):
        return {"kind": "relative", "column_hint": "orders.order_date/refunds.refund_date", "sql": f">= DATE_SUB('{reference_date}', INTERVAL 6 MONTH)"}
    if any(term in question for term in ["最近一年", "过去一年"]):
        return {"kind": "relative", "column_hint": "orders.order_date/refunds.refund_date", "sql": f">= DATE_SUB('{reference_date}', INTERVAL 12 MONTH)"}
    if "最近三个完整自然月" in question:
        return {"kind": "complete_months", "sql": ">= '2026-06-01' AND < '2026-09-01'"}
    if "2026年第二季度" in question:
        return {"kind": "calendar_quarter", "sql": ">= '2026-04-01' AND < '2026-07-01'"}
    if "2025年双十一" in question:
        return {"kind": "explicit_range", "sql": "BETWEEN '2025-11-01' AND '2025-11-30'"}
    if "同比" in question:
        return {"kind": "year_over_year", "sql": "compare full calendar years 2026 vs 2025"}
    return {"kind": "all_time"}


def _detect_ranking(question: str, metric: str) -> Optional[Dict[str, Any]]:
    if any(term in question for term in ["最高", "最多", "排名", "top", "Top", "找几个", "哪些"]):
        return {"metric": metric, "direction": "DESC"}
    if any(term in question for term in ["最低", "最少", "滞销"]):
        return {"metric": metric, "direction": "ASC"}
    return None


def _detect_limit(question: str) -> Optional[int]:
    patterns = [
        r"前\s*(\d+|十|五)\s*(?:个|位|笔|名)?",
        r"(?:top|Top)\s*(\d+|十|五)",
        r"排名前\s*(\d+|十|五)",
        r"最高的\s*(\d+|十|五|几个)\s*(?:个|位|笔|名)?",
        r"最多的\s*(\d+|十|五|几个)\s*(?:个|位|笔|名)?",
        r"找\s*(\d+|十|五|几个)\s*(?:个|位|笔|名)?",
    ]
    match = next((re.search(pattern, question) for pattern in patterns if re.search(pattern, question)), None)
    if not match:
        return None
    value = match.group(1)
    return {"十": 10, "五": 5, "几个": 10}.get(value, int(value) if value.isdigit() else None)


def _detect_filters(question: str, metric: str) -> List[str]:
    filters: List[str] = []
    if metric in {"sales_amount", "avg_order_amount", "arppu", "discount_amount"} or any(term in question for term in ["排除取消", "未支付", "成交", "有效"]):
        filters.append("valid_orders")
    if "取消订单占比" in question:
        filters.append("all_orders_for_status_rate")
    if metric in {"refund_amount", "refund_rate"} and "退款通过率" not in question:
        filters.append("approved_refunds")
    if "在售" in question:
        filters.append("active_products")
    if "VIP" in question or "vip" in question:
        filters.append("users.is_vip = 1")
    for level in ["silver", "gold", "black"]:
        cn = {"silver": "银卡", "gold": "金卡", "black": "黑卡"}[level]
        if cn in question:
            filters.append(f"users.user_level = '{level}'")
    for category in ["手机数码", "家用电器", "美妆个护", "服饰鞋包", "食品生鲜"]:
        if category in question:
            filters.append(f"products.category = '{category}'")
    return _dedupe(filters)


def _required_tables(metric: str, dimensions: List[str], filters: List[str]) -> List[str]:
    tables = set()
    if metric in {"sales_amount", "avg_order_amount", "arppu", "order_count", "discount_amount"}:
        tables.add("orders")
    if metric in {"quantity", "active_product_count", "avg_product_price"}:
        tables.add("products")
        if metric == "quantity":
            tables.add("order_items")
    if metric in {"refund_amount", "refund_rate", "refund_approval_rate"}:
        tables.add("refunds")
    if metric == "refund_rate":
        tables.update({"orders", "order_items", "products"})
    if any(dim in dimensions for dim in ["product", "category", "brand"]):
        tables.add("products")
        if metric != "active_product_count":
            tables.add("order_items")
    if any(dim in dimensions for dim in ["customer", "city", "province", "user_level", "is_vip"]):
        tables.update({"users", "orders"})
    if any(f.startswith("products.") for f in filters):
        tables.add("products")
    if any(f.startswith("users.") for f in filters):
        tables.add("users")
        tables.add("orders")
    if "valid_orders" in filters:
        tables.add("orders")
    return sorted(tables)


def _normalize_terms(question: str) -> Dict[str, str]:
    terms = {}
    if any(term in question for term in ["退货", "被退", "老被退"]):
        terms["退货/被退/老被退"] = "approved refunds; severity usually refund_rate"
    if any(term in question for term in ["卖得最好", "卖得最多"]):
        terms["卖得最好/卖得最多"] = "quantity unless 金额/销售额 is explicit"
    if any(term in question for term in ["大客户", "花钱最多"]):
        terms["大客户/花钱最多"] = "customer ranked by SUM(orders.paid_amount)"
    return terms


def _plan_notes(metric: str, dimensions: List[str], text: str) -> List[str]:
    notes = []
    if metric == "refund_rate":
        notes.append("Build sales denominator and approved refund numerator separately, then LEFT JOIN by product/category.")
    if "product" in dimensions or "category" in dimensions or "brand" in dimensions:
        notes.append("Use product/category/brand names from products; sales amount should usually come from order_items.item_amount.")
    if "city" in dimensions or "province" in dimensions or "customer" in dimensions:
        notes.append("Use users -> orders join and orders.paid_amount for customer/geography sales.")
    if "手机" in text and "手机数码" not in text:
        notes.append("Do not infer 手机数码 unless the exact category appears.")
    return notes


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
