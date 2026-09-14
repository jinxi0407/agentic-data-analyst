"""Run or verify the frozen 300-case Release v1.0 evaluation."""

from __future__ import annotations

import concurrent.futures
import fcntl
import json
import multiprocessing
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.scoring import compare, digest, fingerprint, write_json

TRANSIENT_MARKERS = (
    "timeout", "timed out", "connection reset", "connection refused",
    "temporary failure", "temporarily unavailable", "service unavailable",
    "server disconnected", "remote end closed", "lost connection to mysql",
    "can't connect to mysql server", "too many requests", "rate limit",
    "http 502", "http 503", "http 504",
)
_RUNNER = None


def is_infrastructure_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def grouped_accuracy(results, field):
    output = {}
    for key in sorted({row[field] for row in results}):
        rows = [row for row in results if row[field] == key]
        output[key] = sum(row["correct"] for row in rows) / len(rows)
    return output


def _init_worker() -> None:
    global _RUNNER
    from app.agent.production import run_question

    _RUNNER = run_question


def _run(question: str) -> dict:
    started = time.perf_counter()
    try:
        state = _RUNNER(question)
        return {
            "status": state.get("status", "failed"),
            "actual_result": state.get("result", []),
            "generated_sql": state.get("sql", ""),
            "retry_count": state.get("retry_count", 0),
            "error": state.get("error", ""),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        return {
            "status": "failed", "actual_result": [], "generated_sql": "",
            "retry_count": 0, "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def main() -> None:
    from app.config import settings
    from app.tools.database import fetch_all

    assert settings.qwen_chat_model == "qwen-plus"
    lock = (ROOT / "eval/final_evaluation.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cases = json.loads((ROOT / "eval/final_release_holdout_300.json").read_text())
    manifest = json.loads((ROOT / "eval/final_release_manifest.json").read_text())
    assert manifest["status"] == "FINAL RELEASE HOLDOUT 300 FROZEN"
    assert digest(cases) == manifest["cases_sha256"]
    assert fingerprint(fetch_all) == manifest["database"]

    result_path = ROOT / "eval/final_results.json"
    results = json.loads(result_path.read_text()) if result_path.exists() else []
    done = {row["id"] for row in results}
    assert len(done) == len(results)
    remaining = [case for case in cases if case["id"] not in done]

    if remaining:
        spawn = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=4, mp_context=spawn, initializer=_init_worker
        ) as pool:
            futures = {pool.submit(_run, case["question"]): case for case in remaining}
            for future in concurrent.futures.as_completed(futures):
                case = futures[future]
                payload = future.result()
                if is_infrastructure_error(payload["error"]):
                    raise RuntimeError(
                        f"Transient infrastructure failure for {case['id']}; rerun to resume"
                    )
                results.append(
                    {
                        "id": case["id"], "category": case["category"],
                        "difficulty": case["difficulty"],
                        "paraphrase": case["paraphrase"],
                        "status": payload["status"],
                        "correct": payload["status"] == "success" and compare(
                            case["ground_truth_result"], payload["actual_result"], case["ordered"]
                        ),
                        "generated_sql": payload["generated_sql"],
                        "actual_result": payload["actual_result"],
                        "retry_count": payload["retry_count"],
                        "error": payload["error"],
                        "latency_ms": payload["latency_ms"],
                        "selected_route": "production",
                    }
                )
                write_json(result_path, sorted(results, key=lambda row: row["id"]))
                print(f"production: {len(results)}/300 persisted", flush=True)

    if len(results) != 300:
        raise RuntimeError(f"Production evaluation incomplete: {len(results)}/300")
    assert fingerprint(fetch_all) == manifest["database"]
    report = {
        "pipeline": "production",
        "total": len(results),
        "correct": sum(row["correct"] for row in results),
        "accuracy": sum(row["correct"] for row in results) / len(results),
        "cases_sha256": manifest["cases_sha256"],
        "workers": 4,
        "average_latency_ms": statistics.mean(row["latency_ms"] for row in results),
        "average_retry": statistics.mean(row["retry_count"] for row in results),
        "execution_rate": sum(row["status"] == "success" for row in results) / len(results),
        "difficulty": grouped_accuracy(results, "difficulty"),
        "category": grouped_accuracy(results, "category"),
        "paraphrase_accuracy": sum(row["correct"] for row in results if row["paraphrase"])
        / sum(row["paraphrase"] for row in results),
        "infrastructure_rerun_count": 0,
    }
    write_json(ROOT / "eval/final_report.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

