"""Shared one-pass runner for Strong v2 and Complexity-Aware Hybrid Final."""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import multiprocessing
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_scoring", ROOT / "eval/daily_business.py")
scoring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scoring)

STRONG_V2_SHA256 = "d6765bc00740e42d40e06674622f37fbb27b63b3d38c62d2436804ed8b20adc0"
HYBRID_SHA256 = "c44bd5f9819a1477121f6cd97cb8bb0b6c5fdf7c7cfae91c15837110495aa049"
FINAL_COMMIT = "3d612dfc725e3654094c51aa542aa88d2a55c856"
TRANSIENT_MARKERS = (
    "timeout", "timed out", "connection reset", "connection refused",
    "temporary failure", "temporarily unavailable", "service unavailable",
    "server disconnected", "remote end closed", "lost connection to mysql",
    "can't connect to mysql server", "too many requests", "rate limit",
    "http 502", "http 503", "http 504",
)

_WORKER_RUNNER = None


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_infrastructure_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def grouped_accuracy(results, field):
    output = {}
    for key in sorted({row[field] for row in results}):
        rows = [row for row in results if row[field] == key]
        output[key] = sum(row["correct"] for row in rows) / len(rows)
    return output


def _init_worker(kind: str, root: str, final_implementation: str) -> None:
    global _WORKER_RUNNER
    if kind == "agent":
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                del sys.modules[name]
        sys.path[:] = [final_implementation] + [
            item for item in sys.path if item not in (root, final_implementation)
        ]
        from app.agent.workflow import run_question
    else:
        if root not in sys.path:
            sys.path.insert(0, root)
        from eval.strong_baseline_v2 import run_question
    _WORKER_RUNNER = run_question


def _worker_run(question: str) -> dict:
    started = time.perf_counter()
    try:
        state = _WORKER_RUNNER(question)
    except Exception as exc:
        return {
            "exception": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    result = state.get("result", state.get("query_result", []))
    status = state.get("status", state.get("exec_status", "failed"))
    error = state.get("error") or state.get("execution_error") or state.get("validation_error") or ""
    return {
        "status": status,
        "actual_result": result,
        "generated_sql": state.get("sql", ""),
        "retry_count": state.get("retry_count", 0),
        "error": error,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _failed_row(case: dict, error: str, latency_ms: float, decision: dict) -> dict:
    return {
        "id": case["id"], "category": case["category"],
        "difficulty": case["difficulty"], "paraphrase": case["paraphrase"],
        "status": "failed", "correct": False, "generated_sql": "",
        "actual_result": [], "retry_count": 0, "error": error,
        "latency_ms": latency_ms,
        "selected_route": decision["route"],
        "complexity_score": decision["complexity_score"],
        "routing_reasons": decision["reasons"],
    }


def _validate_frozen_sources(final_implementation: str | None) -> None:
    assert file_sha256(ROOT / "eval/strong_baseline_v2.py") == STRONG_V2_SHA256
    assert file_sha256(ROOT / "eval/hybrid_final.py") == HYBRID_SHA256
    if final_implementation:
        commit = subprocess.check_output(
            ["git", "-C", final_implementation, "rev-parse", "HEAD"], text=True
        ).strip()
        assert commit == FINAL_COMMIT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", choices=("strong_v2", "hybrid"), required=True)
    parser.add_argument("--final-implementation")
    args = parser.parse_args()
    if args.pipeline == "hybrid" and not args.final_implementation:
        parser.error("--final-implementation is required for hybrid")
    _validate_frozen_sources(args.final_implementation)

    sys.path.insert(0, str(ROOT))
    from app.config import settings
    from app.tools.database import fetch_all
    from eval.hybrid_final import route_question

    assert settings.qwen_chat_model == "qwen-plus"
    assert settings.qwen_embedding_model == "text-embedding-v4"
    lock = (ROOT / f"eval/final_release_holdout_300_{args.pipeline}.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cases = json.loads((ROOT / "eval/final_release_holdout_300_cases.json").read_text())
    manifest = json.loads((ROOT / "eval/final_release_holdout_300_manifest.json").read_text())
    assert manifest["status"] == "FINAL RELEASE HOLDOUT 300 FROZEN"
    assert scoring.digest(cases) == manifest["cases_sha256"]
    assert scoring.fingerprint(fetch_all) == manifest["database"]

    checkpoint = ROOT / f"eval/final_release_holdout_300_{args.pipeline}_results.json"
    results = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    done = {row["id"] for row in results}
    assert len(done) == len(results)
    event_path = ROOT / f"eval/final_release_holdout_300_{args.pipeline}_infrastructure_events.json"
    previous_events = json.loads(event_path.read_text()) if event_path.exists() else []
    new_events = []
    decisions = {
        case["id"]: (
            route_question(case["question"]).to_dict()
            if args.pipeline == "hybrid"
            else {"route": "baseline", "complexity_score": 0, "reasons": []}
        )
        for case in cases
    }

    def consume(future, case):
        payload = future.result()
        decision = decisions[case["id"]]
        error = payload.get("exception") or payload.get("error", "")
        if is_infrastructure_error(error):
            prior_count = sum(event["case_id"] == case["id"] for event in previous_events + new_events)
            new_events.append(
                {
                    "case_id": case["id"], "error": error,
                    "rerun_reason": "recognized transient API/network/database infrastructure failure",
                    "rerun_count": prior_count + 1,
                }
            )
            print(f"{args.pipeline}: infrastructure event for {case['id']}; not persisted", flush=True)
            return
        if payload.get("exception"):
            row = _failed_row(case, payload["exception"], payload["latency_ms"], decision)
        else:
            status = payload["status"]
            actual = payload["actual_result"]
            row = {
                "id": case["id"], "category": case["category"],
                "difficulty": case["difficulty"], "paraphrase": case["paraphrase"],
                "status": status,
                "correct": status == "success" and scoring.compare(
                    case["ground_truth_result"], actual, case["ordered"]
                ),
                "generated_sql": payload["generated_sql"],
                "actual_result": actual, "retry_count": payload["retry_count"],
                "error": payload["error"], "latency_ms": payload["latency_ms"],
                "selected_route": decision["route"],
                "complexity_score": decision["complexity_score"],
                "routing_reasons": decision["reasons"],
            }
        results.append(row)
        scoring.write_json(checkpoint, sorted(results, key=lambda item: item["id"]))
        print(f"{args.pipeline}: {len(results)}/300 persisted", flush=True)

    remaining = [case for case in cases if case["id"] not in done]
    spawn = multiprocessing.get_context("spawn")
    if args.pipeline == "strong_v2":
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=4, mp_context=spawn, initializer=_init_worker,
            initargs=("fast", str(ROOT), ""),
        ) as pool:
            futures = {pool.submit(_worker_run, case["question"]): case for case in remaining}
            for future in concurrent.futures.as_completed(futures):
                consume(future, futures[future])
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=2, mp_context=spawn, initializer=_init_worker,
            initargs=("fast", str(ROOT), ""),
        ) as fast_pool, concurrent.futures.ProcessPoolExecutor(
            max_workers=2, mp_context=spawn, initializer=_init_worker,
            initargs=("agent", str(ROOT), args.final_implementation),
        ) as agent_pool:
            futures = {}
            for case in remaining:
                pool = fast_pool if decisions[case["id"]]["route"] == "fast" else agent_pool
                futures[pool.submit(_worker_run, case["question"])] = case
            for future in concurrent.futures.as_completed(futures):
                consume(future, futures[future])

    if new_events:
        scoring.write_json(event_path, previous_events + new_events)
    if len(results) != 300:
        raise RuntimeError(f"{args.pipeline} incomplete: {len(results)}/300; rerun unfinished cases")
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
    if args.pipeline == "hybrid":
        report["routing"] = {}
        for route in ("fast", "agent"):
            rows = [row for row in results if row["selected_route"] == route]
            report["routing"][route] = {
                "count": len(rows), "percentage": len(rows) / len(results),
                "accuracy": sum(row["correct"] for row in rows) / len(rows) if rows else 0,
                "average_latency_ms": statistics.mean(row["latency_ms"] for row in rows) if rows else 0,
            }
        report["complexity_score_distribution"] = dict(
            sorted(Counter(str(row["complexity_score"]) for row in results).items())
        )
    scoring.write_json(ROOT / f"eval/final_release_holdout_300_{args.pipeline}_report.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

