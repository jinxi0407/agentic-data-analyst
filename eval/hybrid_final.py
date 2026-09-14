"""Complexity-aware single-route orchestration over two frozen pipelines."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal


Route = Literal["fast", "agent"]
Runner = Callable[[str], dict[str, Any]]
AGENT_THRESHOLD = 2


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    complexity_score: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


METRIC_GROUPS = {
    "sales": ("销售额", "成交额", "实付金额", "消费金额"),
    "quantity": ("销量", "销售数量", "卖出数量"),
    "orders": ("订单数", "下单量", "订单量"),
    "refund_amount": ("退款金额", "退款额"),
    "refund_rate": ("退款率", "退货率"),
    "customers": ("用户数", "客户数", "付费用户"),
    "average_order": ("客单价", "平均实付", "平均订单"),
    "discount": ("优惠金额", "折扣金额"),
    "cost_or_margin": ("成本", "毛利", "利润"),
}

ENTITY_GROUPS = {
    "customer": ("用户", "客户", "会员"),
    "order": ("订单", "成交单", "下单"),
    "product": ("商品", "产品", "品类", "品牌"),
    "refund": ("退款", "退货", "被退"),
}


def _present_groups(question: str, groups: dict[str, tuple[str, ...]]) -> set[str]:
    return {
        name
        for name, terms in groups.items()
        if any(term in question for term in terms)
    }


def route_question(question: str) -> RouteDecision:
    """Return an explainable decision; straightforward questions remain fast."""
    reasons: list[str] = []
    metrics = _present_groups(question, METRIC_GROUPS)
    entities = _present_groups(question, ENTITY_GROUPS)

    multi_stage = bool(
        re.search(r"先.+(?:再|然后|之后).+", question)
        or re.search(r"找出.+(?:再|然后|之后|比较).+", question)
    )
    if multi_stage:
        reasons.append("multi_stage_analysis")

    if len(metrics) >= 2:
        reasons.append("multiple_business_metrics")

    nested_ranking = bool(
        re.search(r"(?:每个|各(?:个)?).{0,16}(?:中|里)?.{0,12}(?:最高|最低|前\s*\d+|排名)", question)
    )
    if nested_ranking:
        reasons.append("nested_group_ranking")

    derived_metric = bool(re.search(r"(?:率|占比|比例|每位|人均|客单价|同比|环比)", question))
    grouped = bool(re.search(r"(?:按|每个|各(?:个)?|分别)", question))
    if derived_metric and grouped:
        reasons.append("derived_metric_with_grouping")

    if len(entities) >= 3:
        reasons.append("multiple_business_entities")
        reasons.append("probable_multi_hop_relation")

    operations = {
        "group" for _ in [0] if grouped
    } | {
        "rank" for _ in [0] if re.search(r"(?:最高|最低|前\s*\d+|后\s*\d+|排名)", question)
    } | {
        "compare" for _ in [0] if re.search(r"(?:相比|比较|高于|低于|超过|同比|环比)", question)
    } | {
        "derived" for _ in [0] if derived_metric
    } | {
        "stage" for _ in [0] if multi_stage
    }
    if len(operations) >= 3:
        reasons.append("combined_operations")

    if re.search(r"(?:最高且|最低且|分别.+同时|每个.+中.+(?:最高|最低)|找出.+再)", question):
        reasons.append("complex_language_structure")

    score = len(reasons)
    route: Route = "agent" if score >= AGENT_THRESHOLD else "fast"
    return RouteDecision(route=route, complexity_score=score, reasons=tuple(reasons))


def run_question(
    question: str,
    *,
    fast_runner: Runner | None = None,
    agent_runner: Runner | None = None,
) -> dict[str, Any]:
    """Select exactly one frozen pipeline and attach the router trace."""
    decision = route_question(question)
    if decision.route == "fast":
        if fast_runner is None:
            from eval.strong_baseline_v2 import run_question as fast_runner

        selected = fast_runner
    else:
        if agent_runner is None:
            from app.agent.workflow import run_question as agent_runner

        selected = agent_runner

    state = dict(selected(question))
    state.update(
        {
            "selected_route": decision.route,
            "complexity_score": decision.complexity_score,
            "routing_reasons": list(decision.reasons),
        }
    )
    return state

