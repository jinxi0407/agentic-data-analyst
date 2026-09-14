"""Run pure Direct NL2SQL on the frozen Daily Business Benchmark."""

import concurrent.futures
import fcntl
import importlib.util
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("daily_scoring", ROOT / "eval/daily_business.py")
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)

from app.config import settings
from app.schema.metadata import build_schema_text
from app.tools.database import execute_agent_select, fetch_all
from app.tools.guardrail import validate_and_rewrite_sql
from app.tools.qwen import generate_text


SYSTEM_PROMPT = """You generate MySQL 8 SQL.
Return only one SQL query without markdown or explanation.
Only SELECT or WITH ... SELECT is allowed.
Use only the supplied schema and the user's question.
Use the explicit reference date in the question rather than the system date.
Add the requested ORDER BY and LIMIT for ranking questions.
"""


def generate_sql(question: str, schema: str) -> str:
    text = generate_text([
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": f"Full database schema:\n{schema}\n\nQuestion:\n{question}"},
    ], temperature=0.05)
    block = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    bare = re.search(r"((?:WITH|SELECT)[\s\S]*)", text, re.IGNORECASE)
    return (bare.group(1) if bare else text).strip().rstrip(";")


def main() -> None:
    assert settings.qwen_chat_model == "qwen-plus"
    assert settings.qwen_embedding_model == "text-embedding-v4"
    lock = (ROOT / "eval/daily_direct_baseline.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cases = json.loads((ROOT / "eval/daily_business_cases.json").read_text())
    manifest = json.loads((ROOT / "eval/daily_business_manifest.json").read_text())
    assert scoring.digest(cases) == manifest["cases_sha256"]
    assert scoring.fingerprint(fetch_all) == manifest["database"]
    checkpoint = ROOT / "eval/daily_direct_baseline_results.json"
    results = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    done = {row["id"] for row in results}
    assert len(done) == len(results)
    schema = build_schema_text(["users", "products", "orders", "order_items", "refunds"])

    def evaluate(case):
        started = time.perf_counter()
        sql = ""
        actual = []
        status = "failed"
        error = ""
        try:
            sql = generate_sql(case["question"], schema)
            guard = validate_and_rewrite_sql(sql)
            if not guard.ok:
                raise RuntimeError(guard.error)
            sql = guard.sql
            actual = execute_agent_select(sql)
            status = "success"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        return {
            "id": case["id"], "category": case["category"],
            "difficulty": case["difficulty"], "paraphrase": case["paraphrase"],
            "status": status, "correct": status == "success" and scoring.compare(
                case["expected_result"], actual, case["ordered"]),
            "generated_sql": sql, "actual_result": actual, "error": error,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(evaluate, case) for case in cases if case["id"] not in done]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            scoring.write_json(checkpoint, sorted(results, key=lambda row: row["id"]))
            print(f"direct: {len(results)}/250 persisted", flush=True)
    assert scoring.fingerprint(fetch_all) == manifest["database"]

    accuracy = sum(row["correct"] for row in results) / len(results)
    report = {
        "label": "pure_direct_nl2sql", "total": len(results), "accuracy": accuracy,
        "cases_sha256": manifest["cases_sha256"], "workers": 4,
        "average_latency_ms": statistics.mean(row["latency_ms"] for row in results),
        "execution_rate": sum(row["status"] == "success" for row in results) / len(results),
    }
    scoring.write_json(ROOT / "eval/daily_direct_baseline_report.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
