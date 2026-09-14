"""Aggregate with the unchanged scorer; add explicitly denominated subset statistics."""

import json
import statistics

from eval.run_clarification import report
from eval.run_corrected_clarification import ROOT, DATA, RESULTS, REPLIES, validate
from eval.scoring import compare, write_json


def ratio(n,d):
    return {"numerator":n,"denominator":d,"percent":round(100*n/d,2) if d else None}


def summarize(cases, raw):
    rows=[]
    answered=accepted=accepted_correct=answered_correct=0
    for case in cases:
        record=raw[case["id"]]
        baseline=record["v1_0"]["payload"]
        first=record["v1_1_first"]["payload"]
        triggered=first["status"]=="needs_clarification"
        assert not triggered or "v1_1_followup" in record, "Pending user turn"
        followup=record.get("v1_1_followup")
        final=followup["payload"] if followup else first
        correct=final["status"]=="success" and compare(case["ground_truth_result"],final.get("result",[]),case["ordered"])
        baseline_correct=baseline["status"]=="success" and compare(case["ground_truth_result"],baseline.get("result",[]),case["ordered"])
        supplied=followup is not None and final["status"]!="simulated_answer_unavailable"
        passed=supplied and any(t.get("stage")=="clarification" and t.get("status")=="proceed" for t in final.get("trace",[]))
        if case["should_clarify"]:
            answered+=supplied
            answered_correct+=supplied and correct
            accepted+=passed
            accepted_correct+=passed and correct
        failures=[]
        if case["should_clarify"] and not triggered: failures.append("missed_clarification")
        if not case["should_clarify"] and triggered: failures.append("unnecessary_clarification")
        if final["status"] not in ("success","needs_clarification"): failures.append(final["status"])
        if final["status"]=="success" and not correct: failures.append("result_mismatch")
        row={"id":case["id"],"question":case["question"],"should_clarify":case["should_clarify"],
             "first_status":first["status"],"triggered":triggered,"final_status":final["status"],
             "first_latency_s":record["v1_1_first"]["elapsed_s"],
             "total_latency_s":record["v1_1_first"]["elapsed_s"]+(followup["elapsed_s"] if followup else 0),
             "interactive_correct":correct,"baseline_correct":baseline_correct,
             "baseline_latency_s":record["v1_0"]["elapsed_s"],"baseline_status":baseline["status"],
             "actual_clarification_question":first.get("clarification_question",""),
             "followup_supplied":supplied,"gate_accepted_followup":passed,
             "failure_categories":failures,"baseline_sql":baseline.get("sql",""),
             "v1_1_sql":final.get("sql",""),"baseline_result":baseline.get("result",[]),
             "v1_1_result":final.get("result",[]),"ground_truth_result":case["ground_truth_result"]}
        rows.append(row)
    metrics=report(cases,rows)
    metrics["answered_ambiguous_subset_result_accuracy"]=ratio(answered_correct,answered)
    metrics["gate_accepted_ambiguous_subset_result_accuracy"]=ratio(accepted_correct,accepted)
    metrics["gate_accepted_subset_definition"]="Originally ambiguous, received a question-scoped simulated answer, second gate returned proceed; SQL failures remain in denominator."
    metrics["all_ambiguous_task_success"]=ratio(sum(c["should_clarify"] and r["triggered"] and r["interactive_correct"] for c,r in zip(cases,rows)),sum(c["should_clarify"] for c in cases))
    metrics["v1_0_total_correct"]=sum(r["baseline_correct"] for r in rows)
    metrics["v1_1_total_result_correct"]=sum(r["interactive_correct"] for r in rows)
    metrics["v1_1_interactive_success_count"]=sum(r["interactive_correct"] and (not r["should_clarify"] or r["triggered"]) for r in rows)
    metrics["unanswerable_followups"]=sum(r["final_status"]=="simulated_answer_unavailable" for r in rows)
    metrics["v1_0_median_latency_s"]=round(statistics.median(r["baseline_latency_s"] for r in rows),3)
    metrics["v1_1_median_total_latency_s"]=round(statistics.median(r["total_latency_s"] for r in rows),3)
    metrics["latency_note"]="Only system call durations; manual simulated-user review/thinking and time between phases are excluded. Two workers, same host and database."
    return metrics,rows


if __name__=="__main__":
    validate()
    cases=json.loads(DATA.read_text())
    raw=json.loads(RESULTS.read_text())
    metrics,rows=summarize(cases,raw)
    write_json(ROOT/"eval/clarification_corrected_report.json",metrics)
    write_json(ROOT/"eval/clarification_corrected_per_case.json",rows)
    write_json(ROOT/"eval/clarification_corrected_bad_cases.json",[
        r for r in rows if r["failure_categories"] or not r["baseline_correct"]])
    print(json.dumps(metrics,ensure_ascii=False,indent=2))
