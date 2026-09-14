"""Shared runner for Strong Baseline v2 and frozen Final Agent."""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("holdout_v2_scoring", ROOT / "eval/daily_business.py")
scoring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scoring)

TRANSIENT_MARKERS = (
    "timeout", "timed out", "connection reset", "connection refused",
    "temporary failure", "service unavailable", "rate limit", "quota",
    "dashscope", "qwen chat call failed",
)


def is_infrastructure_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def grouped_accuracy(results, field):
    output = {}
    for key in sorted({row[field] for row in results}):
        rows = [row for row in results if row[field] == key]
        output[key] = sum(row["correct"] for row in rows) / len(rows)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", choices=("strong_v2", "final"), required=True)
    parser.add_argument("--final-implementation")
    args = parser.parse_args()
    if args.pipeline == "final":
        if not args.final_implementation:
            parser.error("--final-implementation is required for final")
        sys.path.insert(0, args.final_implementation)
        from app.agent.workflow import run_question
    else:
        sys.path.insert(0, str(ROOT))
        from eval.strong_baseline_v2 import run_question

    from app.config import settings
    from app.tools.database import fetch_all

    assert settings.qwen_chat_model == "qwen-plus"
    assert settings.qwen_embedding_model == "text-embedding-v4"
    lock = (ROOT / f"eval/final_holdout_v2_{args.pipeline}.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cases = json.loads((ROOT / "eval/final_holdout_v2_cases.json").read_text())
    manifest = json.loads((ROOT / "eval/final_holdout_v2_manifest.json").read_text())
    assert manifest["status"] == "FINAL HOLDOUT V2 FROZEN"
    assert scoring.digest(cases) == manifest["cases_sha256"]
    assert scoring.fingerprint(fetch_all) == manifest["database"]
    checkpoint = ROOT / f"eval/final_holdout_v2_{args.pipeline}_results.json"
    results = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    done = {row["id"] for row in results}
    assert len(done) == len(results)
    event_path = ROOT / f"eval/final_holdout_v2_{args.pipeline}_infrastructure_events.json"
    previous_events = json.loads(event_path.read_text()) if event_path.exists() else []
    new_events = []

    def evaluate(case):
        started = time.perf_counter()
        try:
            state = run_question(case["question"])
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if is_infrastructure_error(message):
                return {"case_id": case["id"], "infrastructure_error": message}
            return failed_row(case, message, started)
        actual = state.get("result", state.get("query_result", []))
        status = state.get("status", state.get("exec_status", "failed"))
        error = state.get("error") or state.get("execution_error") or state.get("validation_error") or ""
        if status in ("error", "failed") and is_infrastructure_error(error):
            return {"case_id": case["id"], "infrastructure_error": error}
        return {
            "id": case["id"], "category": case["category"],
            "difficulty": case["difficulty"], "paraphrase": case["paraphrase"],
            "status": status,
            "correct": status == "success" and scoring.compare(
                case["ground_truth_result"], actual, case["ordered"]),
            "generated_sql": state.get("sql", ""), "actual_result": actual,
            "retry_count": state.get("retry_count", 0), "error": error,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def failed_row(case, error, started):
        return {
            "id": case["id"], "category": case["category"],
            "difficulty": case["difficulty"], "paraphrase": case["paraphrase"],
            "status": "failed", "correct": False, "generated_sql": "",
            "actual_result": [], "retry_count": 0, "error": error,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(evaluate, case): case for case in cases if case["id"] not in done}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            if row.get("infrastructure_error"):
                prior_count = sum(event["case_id"] == row["case_id"] for event in previous_events + new_events)
                new_events.append(
                    {
                        "case_id": row["case_id"], "error": row["infrastructure_error"],
                        "rerun_reason": "recognized transient API/network/database infrastructure failure",
                        "rerun_count": prior_count + 1,
                    }
                )
                print(f"{args.pipeline}: infrastructure event for {row['case_id']}; not persisted", flush=True)
                continue
            results.append(row)
            scoring.write_json(checkpoint, sorted(results, key=lambda item: item["id"]))
            print(f"{args.pipeline}: {len(results)}/250 persisted", flush=True)
    if new_events:
        scoring.write_json(event_path, previous_events + new_events)
    if len(results) != 250:
        raise RuntimeError(f"{args.pipeline} incomplete: {len(results)}/250; rerun unfinished cases")
    assert scoring.fingerprint(fetch_all) == manifest["database"]
    report = {
        "pipeline": args.pipeline,
        "total": len(results), "correct": sum(row["correct"] for row in results),
        "accuracy": sum(row["correct"] for row in results) / len(results),
        "cases_sha256": manifest["cases_sha256"], "workers": 4,
        "average_latency_ms": statistics.mean(row["latency_ms"] for row in results),
        "average_retry": statistics.mean(row["retry_count"] for row in results),
        "execution_rate": sum(row["status"] == "success" for row in results) / len(results),
        "difficulty": grouped_accuracy(results, "difficulty"),
        "category": grouped_accuracy(results, "category"),
        "paraphrase_accuracy": sum(row["correct"] for row in results if row["paraphrase"])
        / sum(row["paraphrase"] for row in results),
        "infrastructure_rerun_count": len(previous_events) + len(new_events),
    }
    scoring.write_json(ROOT / f"eval/final_holdout_v2_{args.pipeline}_report.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
