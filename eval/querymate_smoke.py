"""Run the predeclared release API checks once; never retry model requests."""

import hashlib
import json
from pathlib import Path
import time

import requests

from eval.scoring import write_json


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval/querymate_smoke_protocol.json"
OUTPUT = ROOT / "eval/querymate_smoke_results.json"


def main():
    protocol = json.loads(PROTOCOL.read_text())
    evidence = {
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "actual_browser_acceptance": "pending; API tests are not browser acceptance",
        "attempts": [],
    }
    # Exclusive creation prevents accidental repeat Qwen calls after an interruption.
    with OUTPUT.open("x") as stream:
        json.dump(evidence, stream)

    def call(name, body):
        attempt = {"name": name, "request": body, "state": "started"}
        evidence["attempts"].append(attempt)
        write_json(OUTPUT, evidence)
        started = time.perf_counter()
        try:
            response = requests.post(protocol["endpoint"], json=body, timeout=(5, 120))
            payload = response.json()
            attempt.update(http_status=response.status_code, response=payload, state="completed")
        except (requests.RequestException, ValueError) as exc:
            payload = {}
            attempt.update(state="error", error_type=type(exc).__name__)
        attempt["elapsed_s"] = time.perf_counter() - started
        write_json(OUTPUT, evidence)
        print(json.dumps({"name": name, "state": attempt["state"],
                          "status": payload.get("status"),
                          "elapsed_s": round(attempt["elapsed_s"], 3)}, ensure_ascii=False), flush=True)
        return payload

    clear = protocol["clear_question"]
    ambiguous = protocol["ambiguous_question"]
    call("clear_on", {"question": clear, "mode": "clarify"})
    pending = call("ambiguous_on", {"question": ambiguous, "mode": "clarify"})
    context = pending.get("clarification_context")
    question = pending.get("clarification_question", "")
    if pending.get("status") == "needs_clarification" and context and "城市" in question:
        for name, answer in (("valid_followup", protocol["valid_answer"]),
                             ("invalid_followup", protocol["invalid_answer"])):
            call(name, {"question": ambiguous, "mode": "clarify",
                        "clarification_context": context, "clarification_answer": answer})
    else:
        evidence["followup_skipped_reason"] = "Gate did not request the predeclared missing city; do not invent a replacement answer"
    call("clear_off", {"question": clear, "mode": "direct"})
    evidence["state"] = "finished"
    write_json(OUTPUT, evidence)


if __name__ == "__main__":
    main()
