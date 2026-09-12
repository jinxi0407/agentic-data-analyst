"""Run golden-question evaluation against the local API-free workflow."""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.workflow import run_question


def main() -> None:
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    results = []
    for case in cases:
        started = time.time()
        try:
            state = run_question(case["question"])
            executed = state.get("status") == "success"
            results.append(
                {
                    "question": case["question"],
                    "category": case["category"],
                    "executed": executed,
                    "retry_count": state.get("retry_count", 0),
                    "latency_ms": int((time.time() - started) * 1000),
                    "matched_tables": state.get("matched_tables", []),
                    "sql": state.get("sql", ""),
                    "error": state.get("execution_error") or state.get("validation_error"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "question": case["question"],
                    "category": case["category"],
                    "executed": False,
                    "retry_count": None,
                    "latency_ms": int((time.time() - started) * 1000),
                    "matched_tables": [],
                    "sql": "",
                    "error": str(exc),
                }
            )

    total = len(results)
    executed = sum(1 for item in results if item["executed"])
    repair_success = sum(1 for item in results if item["executed"] and item.get("retry_count", 0) > 0)
    avg_retry = sum((item.get("retry_count") or 0) for item in results) / total
    avg_latency = sum(item["latency_ms"] for item in results) / total
    report = {
        "total": total,
        "sql_execution_rate": round(executed / total, 4) if total else 0,
        "execution_accuracy": round(executed / total, 4) if total else 0,
        "repair_success_count": repair_success,
        "average_retry": round(avg_retry, 2),
        "average_latency_ms": round(avg_latency, 2),
        "results": results,
    }
    output = ROOT / "eval" / "last_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
