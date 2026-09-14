"""Checkpointed, single-run clarification evaluation; no failure rerolls."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import fcntl
import json
from pathlib import Path
import statistics
import time

from app.agent.clarification import ClarificationContext
from app.agent.production import run_interactive, run_question
from app.config import settings
from app.tools.database import fetch_all
from eval.clarification_benchmark import code_digest
from eval.scoring import compare, digest, fingerprint, write_json

ROOT = Path(__file__).resolve().parents[1]


def percent(numerator, denominator):
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def report(cases, results):
    by_id = {row["id"]: row for row in results}
    paired = [(c, by_id[c["id"]]) for c in cases if c["id"] in by_id]
    tp = sum(c["should_clarify"] and r["triggered"] for c, r in paired)
    fp = sum(not c["should_clarify"] and r["triggered"] for c, r in paired)
    fn = sum(c["should_clarify"] and not r["triggered"] for c, r in paired)
    negatives = sum(not c["should_clarify"] for c, _ in paired)
    positives = len(paired) - negatives
    tn = sum(not c["should_clarify"] and r["first_status"] in ("success", "failed") for c, r in paired)
    successful = sum(r["interactive_correct"] and (not c["should_clarify"] or r["triggered"]) for c, r in paired)
    baseline = [r for _, r in paired if "baseline_correct" in r]
    return dict(count=len(paired), decision_accuracy=percent(tp+tn, len(paired)),
        precision=percent(tp, tp+fp), recall=percent(tp, tp+fn), f1=percent(2*tp, 2*tp+fp+fn),
        unnecessary_clarification_rate=percent(fp, negatives), missed_clarification_rate=percent(fn, positives),
        clear_query_e2e_accuracy=percent(sum(not c["should_clarify"] and r["interactive_correct"] for c,r in paired), negatives),
        post_clarification_e2e_accuracy=percent(sum(c["should_clarify"] and r["triggered"] and r["interactive_correct"] for c,r in paired), positives),
        overall_interactive_success_rate=percent(successful, len(paired)),
        overall_result_accuracy=percent(sum(r["interactive_correct"] for _,r in paired),len(paired)),
        trigger_rate=percent(tp+fp,len(paired)),
        average_first_turn_latency_s=round(statistics.mean(r["first_latency_s"] for _,r in paired),3) if paired else 0,
        average_total_latency_s=round(statistics.mean(r["total_latency_s"] for _,r in paired),3) if paired else 0,
        average_resolved_total_latency_s=round(statistics.mean([r["total_latency_s"] for _,r in paired if r["triggered"]]) ,3) if tp+fp else 0,
        baseline_e2e_accuracy=percent(sum(r["baseline_correct"] for r in baseline),len(baseline)) if baseline else None,
        baseline_average_latency_s=round(statistics.mean(r["baseline_latency_s"] for r in baseline),3) if baseline else None,
        baseline_clear_accuracy=percent(sum(not c["should_clarify"] and r.get("baseline_correct",False) for c,r in paired), negatives),
        baseline_ambiguous_accuracy=percent(sum(c["should_clarify"] and r.get("baseline_correct",False) for c,r in paired), positives),
        confusion=dict(tp=tp,fp=fp,fn=fn,tn=tn),
        service_failures=sum(r["first_status"] in ["clarification_unavailable","error"] for _,r in paired),
        note="All intended ambiguous cases form the post-clarification denominator. Interactive success requires clarification for ambiguous inputs plus correct final results; lucky guesses are only included in overall_result_accuracy. Clear unexpected clarification has no simulated answer and fails.")


def evaluate(case, reference, mode, existing):
    row = dict(existing or {"id": case["id"]})
    if mode == "baseline":
        started = time.perf_counter()
        try:
            result = run_question(f"参考日期：{reference.isoformat()}。\n{case['question']}")
            row.update(baseline_correct=result["status"] == "success" and compare(case["ground_truth_result"], result["result"], case["ordered"]),
                       baseline_sql=result.get("sql", ""), baseline_result=result.get("result", []), baseline_status=result["status"],
                       baseline_retry=result.get("retry_count",0))
        except Exception as exc:
            row.update(baseline_correct=False, baseline_status="error", baseline_error_type=type(exc).__name__)
        row["baseline_latency_s"] = round(time.perf_counter()-started,3)
        return row
    started = time.perf_counter()
    try:
        first = run_interactive(case["question"], reference_date=reference)
        row.update(first_status=first["status"], triggered=first["status"]=="needs_clarification",
                   first_latency_s=round(time.perf_counter()-started,3),
                   clarification_question=first.get("clarification_question",""),
                   gate_error=first.get("error","") if first["status"]=="clarification_unavailable" else "",
                   first_trace=first.get("trace",[]))
        result = first
        if row["triggered"] and case["clarification_answer"]:
            context = ClarificationContext.model_validate(first["clarification_context"])
            result = run_interactive(case["question"],case["clarification_answer"],context)
        row.update(interactive_correct=result["status"]=="success" and compare(case["ground_truth_result"],result["result"],case["ordered"]),
                   final_status=result["status"], sql=result.get("sql",""), result=result.get("result",[]),
                   retry_count=result.get("retry_count",0))
    except Exception as exc:
        row.update(first_status="error",triggered=False,first_latency_s=round(time.perf_counter()-started,3),
                   interactive_correct=False,final_status="error",error_type=type(exc).__name__)
    row["total_latency_s"] = round(time.perf_counter()-started,3)
    return row


def run(split, workers):
    path=ROOT / f"eval/clarification_{split}.json"
    cases=json.loads(path.read_text())
    manifest=json.loads(path.with_name(path.stem+"_manifest.json").read_text())
    assert digest(cases)==manifest["cases_sha256"], "Frozen cases changed"
    assert code_digest()==manifest["gate_code_sha256"], "Gate changed after dataset freeze"
    assert settings.qwen_chat_model=="qwen-plus", "Frozen model differs"
    assert fingerprint(fetch_all)==manifest["database"], "Database changed"
    result_path=path.with_name(path.stem+"_results.json")
    rows=json.loads(result_path.read_text()) if result_path.exists() else []
    by_id={row["id"]:row for row in rows}
    assert len(by_id)==len(rows) and set(by_id).issubset({c["id"] for c in cases})
    reference=date.fromisoformat(manifest["reference_date"])
    for mode in ["interactive"] + (["baseline"] if split=="holdout" else []):
        key="baseline_correct" if mode=="baseline" else "interactive_correct"
        pending=[c for c in cases if key not in by_id.get(c["id"],{})]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(evaluate,c,reference,mode,by_id.get(c["id"])) for c in pending]
            for future in as_completed(futures):
                row=future.result()
                by_id[row["id"]]=row
                ordered=[by_id[c["id"]] for c in cases if c["id"] in by_id]
                write_json(result_path,ordered)
                print(f"{split} {mode}: {sum(key in r for r in by_id.values())}/{len(cases)}",flush=True)
    assert fingerprint(fetch_all)==manifest["database"], "Database changed during evaluation"
    metrics=report(cases,list(by_id.values()))
    write_json(path.with_name(path.stem+"_report.json"),metrics)
    print(json.dumps(metrics,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("split",choices=["dev","holdout"])
    parser.add_argument("--workers",type=int,default=2)
    args=parser.parse_args()
    with (ROOT / f"eval/clarification_{args.split}.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run(args.split,args.workers)
