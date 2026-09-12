"""Lightweight skill routing for the single-agent workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Dict


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills"


def route_skill(question: str) -> Dict[str, str]:
    text = question.lower()
    if any(word in text for word in ["退款", "退货", "refund", "退款率"]):
        name = "refund_analysis"
    elif any(word in text for word in ["趋势", "环比", "同比", "月份", "每月", "过去", "最近三个月", "六个月"]):
        name = "trend_analysis"
    else:
        name = "sales_analysis"

    return {"skill_name": name, "skill_content": read_skill(name)}


def read_skill(skill_name: str) -> str:
    path = SKILL_ROOT / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
