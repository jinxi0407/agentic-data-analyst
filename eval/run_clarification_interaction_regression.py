"""One fixed pair of serial sessions per case; local diagnostics only."""

import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import requests

from app.agent.diagnostics import redact
from app.tools.database import fetch_all
from eval.scoring import compare, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs/clarification/interaction_regression"
PROTOCOL = ROOT / "eval/clarification_interaction_regression.json"


def hashes():
    names = ["app/agent/scoped_clarification.py", "app/agent/diagnostics.py", "app/main.py", "ui/app.py",
             "eval/strong_baseline.py", "eval/strong_baseline_v2.py", "app/tools/guardrail.py", "eval/scoring.py"]
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}


def main():
    OUT.mkdir()  # Never overwrite completed attempts or restart silently.
    protocol = json.loads(PROTOCOL.read_text())
    frozen = {"protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(), "code_hashes": hashes(),
              "reference_results": {c["id"]: fetch_all(c["reference_sql"]) if c["reference_sql"] else None
                                    for c in protocol["cases"]}}
    write_json(OUT/"freeze.json", frozen)
    rows = []
    def call(row, stage, body, parent=""):
        rid = str(uuid4())
        step = {"stage": stage, "request_id": rid, "state": "started", "body": body}
        row["steps"].append(step)
        write_json(OUT/"attempts.json", redact(rows))
        start = time.perf_counter()
        try:
            r = requests.post("http://127.0.0.1:8002/api/scoped-query", json=body,
                              headers={"X-Request-ID": rid, "X-Parent-Request-ID": parent}, timeout=(5, 120))
            p = r.json()
            step.update(response=p, http=r.status_code, state="completed")
        except (requests.RequestException, ValueError) as exc:
            p = {"status": "transport_error"}
            step.update(response=p, error_type=type(exc).__name__, state="failed")
        step["latency_s"] = time.perf_counter()-start
        write_json(OUT/"attempts.json", redact(rows))
        return p, rid
    for case in protocol["cases"]:
        for repeat in (1, 2):
            assert hashes() == frozen["code_hashes"], "Runtime changed; stop, do not compare versions"
            row = {"id": case["id"], "repeat": repeat, "steps": []}
            rows.append(row)
            p, rid = call(row, "initial", {"question": case["question"], "mode": "clarify"})
            row["initial_ok"] = p.get("status") == case["initial"]
            if p.get("status") == "needs_clarification" and "answer" in case:
                context = p["clarification_context"]
                if set(context["missing_slots"]) == {case["slot"]}:
                    p, _ = call(row, "followup", {"question": case["question"], "mode": "clarify",
                        "clarification_context": context, "clarification_answer": case["answer"]}, rid)
                else:
                    row["answer_not_sent"] = "Asked slots do not match the predeclared answer; do not fabricate information"
            row["final_status"] = p.get("status")
            expected = frozen["reference_results"][case["id"]]
            row["result_matches_reference"] = (compare(expected, p.get("result", []), case["ordered"])
                                                 if p.get("status") == "success" and expected is not None else None)
            row["check_passed"] = row["initial_ok"] and p.get("status") == case["final"] and (
                row["result_matches_reference"] is True if expected is not None else not p.get("sql"))
            row["latency_s"] = sum(s["latency_s"] for s in row["steps"])
            write_json(OUT/"attempts.json", redact(rows))
            print(json.dumps({k:v for k,v in row.items() if k!="steps"}), flush=True)
    write_json(OUT/"completed.json", {"sessions": len(rows), "http_calls": sum(len(r["steps"]) for r in rows),
                                     "code_hashes_unchanged": hashes()==frozen["code_hashes"]})


if __name__ == "__main__":
    main()
