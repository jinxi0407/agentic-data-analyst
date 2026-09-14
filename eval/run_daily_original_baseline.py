"""Run the adapted original open-source graph on the frozen benchmark once."""

import concurrent.futures
import fcntl
import importlib.util
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("daily_scoring", ROOT / "eval/daily_business.py")
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)

from app.config import settings
from app.tools.database import fetch_all
from eval.original_open_source_baseline import run_question


def grouped_accuracy(results, field):
    return {
        key: sum(row["correct"] for row in rows) / len(rows)
        for key in sorted({row[field] for row in results})
        if (rows := [row for row in results if row[field] == key])
    }


def main() -> None:
    assert settings.qwen_chat_model == "qwen-plus"
    assert settings.qwen_embedding_model == "text-embedding-v4"
    lock = (ROOT / "eval/daily_original_baseline.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cases = json.loads((ROOT / "eval/daily_business_cases.json").read_text())
    manifest = json.loads((ROOT / "eval/daily_business_manifest.json").read_text())
    assert scoring.digest(cases) == manifest["cases_sha256"]
    assert scoring.fingerprint(fetch_all) == manifest["database"]
    checkpoint = ROOT / "eval/daily_original_baseline_results.json"
    results = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    done = {row["id"] for row in results}
    assert len(done) == len(results)

    def evaluate(case):
        started = time.perf_counter()
        try:
            state = run_question(case["question"])
        except Exception as exc:
            state = {"exec_status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        actual = state.get("result", [])
        return {
            "id": case["id"],
            "category": case["category"],
            "difficulty": case["difficulty"],
            "paraphrase": case["paraphrase"],
            "status": state.get("exec_status"),
            "correct": state.get("exec_status") == "success" and scoring.compare(
                case["expected_result"], actual, case["ordered"]
            ),
            "matched_tables": [table["table_name"] for table in state.get("matched_tables", [])],
            "generated_sql": state.get("sql", ""),
            "actual_result": actual,
            "retry_count": state.get("retry_count", 0),
            "error": state.get("error", ""),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(evaluate, case) for case in cases if case["id"] not in done]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            scoring.write_json(checkpoint, sorted(results, key=lambda row: row["id"]))
            print(f"original: {len(results)}/250 persisted", flush=True)
    assert len(results) == 250
    assert scoring.fingerprint(fetch_all) == manifest["database"]

    report = {
        "label": "original_open_source_baseline",
        "upstream_commit": "eaafb8426fee4905953ac52f0ed2cea0f333a0f6",
        "total": len(results),
        "accuracy": sum(row["correct"] for row in results) / len(results),
        "cases_sha256": manifest["cases_sha256"],
        "workers": 4,
        "average_latency_ms": statistics.mean(row["latency_ms"] for row in results),
        "average_retry": statistics.mean(row["retry_count"] for row in results),
        "execution_rate": sum(row["status"] == "success" for row in results) / len(results),
        "no_match_count": sum(row["status"] == "pending" for row in results),
        "difficulty": grouped_accuracy(results, "difficulty"),
        "category": grouped_accuracy(results, "category"),
        "paraphrase_accuracy": sum(row["correct"] for row in results if row["paraphrase"])
        / sum(row["paraphrase"] for row in results),
        "retrieved_table_counts": dict(Counter(table for row in results for table in row["matched_tables"])),
    }
    scoring.write_json(ROOT / "eval/daily_original_baseline_report.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
