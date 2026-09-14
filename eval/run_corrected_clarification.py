"""Staged evaluation with reviewed, question-scoped simulated replies.

The scorer and tested systems are imported unchanged. No reference data is passed
to them. Initial calls finish before reply review; review sees no SQL or scores.
"""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date
import fcntl
import json
from pathlib import Path
import subprocess
import time

from app.agent.clarification import ClarificationContext
from app.agent.production import run_interactive, run_question
from app.config import settings
from eval.audit_clarification_cities import ROOT, check_systems, sha
from app.tools.database import fetch_all
from eval.scoring import compare, fingerprint, write_json

DATA = ROOT / "eval/clarification_holdout_corrected.json"
AUDIT = ROOT / "eval/clarification_city_audit.json"
FREEZE = ROOT / "eval/clarification_corrected_freeze.json"
RESULTS = ROOT / "eval/clarification_corrected_raw_results.json"
REPLIES = ROOT / "eval/clarification_simulated_replies.json"


def validate():
    frozen = json.loads(FREEZE.read_text())
    audit = json.loads(AUDIT.read_text())
    assert check_systems() == audit["system_files_sha256"]
    assert settings.qwen_chat_model == frozen["chat_model"] == "qwen-plus"
    assert settings.dashscope_base_url == frozen["base_url"]
    assert fingerprint(fetch_all) == audit["database"]
    for name, expected in frozen["files_sha256"].items():
        assert sha(ROOT/name) == expected, f"Frozen artifact changed: {name}"
        assert (ROOT/name).read_bytes() == subprocess.check_output(
            ["git", "show", frozen["data_commit"]+":"+name], cwd=ROOT)
    for name, expected in audit["original_files_sha256"].items():
        assert sha(ROOT/name) == expected, "Original evidence changed"
    return frozen


def first_call(question, reference, version):
    started = time.perf_counter()
    try:
        if version == "v1_0":
            payload = run_question(f"参考日期：{reference.isoformat()}。\n{question}")
        else:
            payload = run_interactive(question, reference_date=reference)
    except Exception as exc:
        payload = {"status": "error", "error_type": type(exc).__name__, "result": []}
    return {"phase_state": "complete", "payload": payload,
            "elapsed_s": round(time.perf_counter()-started, 6)}


def followup_call(question, context, answer):
    started = time.perf_counter()
    try:
        payload = run_interactive(question, answer, ClarificationContext.model_validate(context))
    except Exception as exc:
        payload = {"status": "error", "error_type": type(exc).__name__, "result": []}
    return {"phase_state": "complete", "payload": payload,
            "elapsed_s": round(time.perf_counter()-started, 6)}


def persist(results):
    write_json(RESULTS, results)


def execute_jobs(jobs, results, workers):
    pending = iter(jobs)
    running = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        def schedule():
            job = next(pending, None)
            if job is None:
                return False
            case_id, phase, fn, args = job
            results.setdefault(case_id, {})[phase] = {"phase_state": "started"}
            persist(results)
            running[pool.submit(fn, *args)] = (case_id, phase)
            return True
        for _ in range(workers):
            schedule()
        while running:
            completed, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in completed:
                case_id, phase = running.pop(future)
                results[case_id][phase] = future.result()
                persist(results)
                print(f"Saved {case_id} {phase}", flush=True)
                schedule()


def review_packet(cases, results):
    packet = []
    for case in cases:
        first = results[case["id"]]["v1_1_first"]["payload"]
        if first["status"] == "needs_clarification":
            packet.append({"case_id": case["id"], "original_question": case["question"],
                           "asked_question": first["clarification_question"],
                           "available_user_answer": case["clarification_answer"]})
    write_json(ROOT/"eval/clarification_reply_review_packet.json", packet)
    print(f"Reply review required for {len(packet)} actual clarifications. No answers sent yet.")


def checked_reply(case, first, reply):
    assert reply["asked_question"] == first["clarification_question"]
    segments = reply["segments"]
    assert isinstance(segments, list) and all(isinstance(s,str) and s for s in segments)
    source = case["clarification_answer"] or ""
    assert all(segment in source for segment in segments), "Reply adds facts absent from fixed simulated answer"
    assert reply["review_reason"], "A relevance review is required"
    if not reply["answerable"]:
        assert not segments
        return None
    assert segments
    return "；".join(segments)


def run(phase, workers):
    frozen = validate()
    cases = json.loads(DATA.read_text())
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    assert set(results).issubset({c["id"] for c in cases})
    # An interrupted in-flight call is retained as a failure, never silently rerolled.
    for row in results.values():
        for entry in row.values():
            if isinstance(entry,dict) and entry.get("phase_state") == "started":
                entry.update(phase_state="complete", payload={"status":"interrupted","result":[]}, elapsed_s=0)
    reference = date.fromisoformat(frozen["reference_date"])
    if phase == "initial":
        jobs = []
        for case in cases:
            for version, key in [("v1_0","v1_0"),("v1_1","v1_1_first")]:
                if key not in results.get(case["id"],{}):
                    jobs.append((case["id"],key,first_call,(case["question"],reference,version)))
        execute_jobs(jobs,results,workers)
        review_packet(cases,results)
    else:
        replies = json.loads(REPLIES.read_text())
        by_id = {r["case_id"]:r for r in replies}
        assert len(by_id) == len(replies)
        expected = {c["id"] for c in cases if results[c["id"]]["v1_1_first"]["payload"]["status"]=="needs_clarification"}
        assert set(by_id)==expected
        reply_lock = ROOT/"eval/clarification_reply_freeze.json"
        if reply_lock.exists():
            assert json.loads(reply_lock.read_text())["reply_sha256"] == sha(REPLIES)
        else:
            write_json(reply_lock,{"reply_sha256":sha(REPLIES),"dataset_sha256":sha(DATA),
                                   "rule":"Verbatim segments only; relevance reviewed before any follow-up execution"})
        jobs=[]
        for case in cases:
            row=results[case["id"]]
            first=row["v1_1_first"]["payload"]
            if first["status"]!="needs_clarification" or "v1_1_followup" in row:
                continue
            answer=checked_reply(case,first,by_id[case["id"]])
            if answer is None:
                row["v1_1_followup"]={"phase_state":"complete","elapsed_s":0,
                    "payload":{"status":"simulated_answer_unavailable","result":[]}}
                persist(results)
            else:
                jobs.append((case["id"],"v1_1_followup",followup_call,
                             (case["question"],first["clarification_context"],answer)))
        execute_jobs(jobs,results,workers)
    assert fingerprint(fetch_all)==json.loads(AUDIT.read_text())["database"]
    print(f"Completed {phase}. Database fingerprint unchanged.")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["initial","followup"])
    parser.add_argument("--workers",type=int,default=2)
    args=parser.parse_args()
    with (ROOT/"eval/clarification_corrected.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run(args.phase,args.workers)
