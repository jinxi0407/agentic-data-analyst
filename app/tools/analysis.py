"""Deterministic Pandas analysis helpers."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def analyze_rows(skill_name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"summary": "查询结果为空。", "metrics": {}}

    df = pd.DataFrame(rows)
    metrics: Dict[str, Any] = {"row_count": int(len(df))}

    for col in df.columns:
        if any(token in col.lower() for token in ["amount", "revenue", "sales"]):
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().any():
                metrics[f"{col}_sum"] = round(float(numeric.sum()), 2)
                metrics[f"{col}_max"] = round(float(numeric.max()), 2)

    if skill_name == "refund_analysis":
        for col in df.columns:
            if "refund_rate" in col.lower():
                numeric = pd.to_numeric(df[col], errors="coerce")
                if numeric.notna().any():
                    metrics["max_refund_rate"] = round(float(numeric.max()), 4)

    return {"summary": _summary_from_metrics(skill_name, metrics), "metrics": metrics}


def _summary_from_metrics(skill_name: str, metrics: Dict[str, Any]) -> str:
    label = {
        "sales_analysis": "销售分析",
        "refund_analysis": "退款分析",
        "trend_analysis": "趋势分析",
    }.get(skill_name, "数据分析")
    return f"{label}已完成，返回 {metrics.get('row_count', 0)} 行结果。"
