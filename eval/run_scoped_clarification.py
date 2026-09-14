"""One-shot paired evaluation; judge artifacts never enter candidate calls."""

import argparse
from collections import Counter
from datetime import date
import fcntl
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

from app.agent.scoped_clarification import Context, direct, run_interactive
from app.config import settings
from app.tools.database import fetch_all
from app.tools.qwen import capture_usage
from eval.scoring import compare, fingerprint, write_json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"eval/scoped_clarification_cases.json"
FREEZE=ROOT/"eval/scoped_clarification_freeze.json"
RAW=ROOT/"eval/scoped_clarification_raw.json"
REPLIES=ROOT/"eval/scoped_reply_review.json"


def read(path): return json.loads(path.read_text())


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def validate():
    f=read(FREEZE)
    for path,h in f["hashes"].items():
        assert sha(ROOT/path)==h, f"Frozen artifact changed: {path}"
    assert settings.qwen_chat_model==f["chat_model"]
    assert settings.qwen_embedding_model==f["embedding_model"]
    assert fingerprint(fetch_all)==f["database"], "Database fingerprint changed"
    return f


def first_call(question, reference, mode):
    # Deliberately cannot receive labels, SQL, expected result or persona intent.
    if mode=="baseline": return direct(question,reference)
    return run_interactive(question,reference_date=reference)


def followup_call(question, context, answer):
    return run_interactive(question,answer,Context.model_validate(context))


def execute(raw, cid, stage, fn):
    record=raw.setdefault(cid,{})
    if stage in record:
        if record[stage]["state"]=="started":
            record[stage].update(state="complete",payload={"status":"system_error","result":[],
                "error":"Interrupted after start; not rerun"},elapsed_s=None,usage=[])
            write_json(RAW,raw)
        return
    record[stage]={"state":"started"}
    write_json(RAW,raw)
    started=time.perf_counter()
    with capture_usage() as usage:
        try: payload=fn()
        except Exception as e: payload={"status":"system_error","result":[],"error":type(e).__name__}
    record[stage]={"state":"complete","payload":payload,"elapsed_s":round(time.perf_counter()-started,6),"usage":usage}
    write_json(RAW,raw)


def first():
    freeze=validate();cases=read(DATA);raw=read(RAW) if RAW.exists() else {}
    runfreeze=ROOT/"eval/scoped_run_freeze.json"
    if not runfreeze.exists():
        assert not raw
        commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        tracked=subprocess.check_output(["git","show",f"{commit}:eval/scoped_clarification_cases.json"],cwd=ROOT)
        assert hashlib.sha256(tracked).hexdigest()==sha(DATA)
        write_json(runfreeze,{"data_commit":commit,"code_commit":freeze["code_commit"],
                             "manifest_sha256":sha(FREEZE),"started_utc":time.time()})
    else:
        assert read(runfreeze)["manifest_sha256"]==sha(FREEZE)
    reference=date.fromisoformat(freeze["reference_date"])
    for i,c in enumerate(cases):
        for mode in (["baseline","first"] if i%2==0 else ["first","baseline"]):
            execute(raw,c["id"],mode,lambda c=c,mode=mode:first_call(c["question"],reference,mode))
        if (i+1)%10==0: print(f"Completed paired first rounds {i+1}/120",flush=True)
    packet=[]
    for c in cases:
        p=raw[c["id"]]["first"]["payload"]
        if p["status"]=="needs_clarification":
            packet.append({"id":c["id"],"original_question":c["question"],
                           "actual_question":p["clarification_question"],
                           "persona_answer":c["persona_answer"]})
    write_json(ROOT/"eval/scoped_reply_packet.json",packet)
    print(f"Review packet: {len(packet)} actual clarification questions",flush=True)


def checked_answer(item, packet):
    assert item["actual_question"]==packet["actual_question"]
    assert item["reason"].strip()
    if not item["valid_question"]:
        assert not item["answer_segments"]
        return None
    assert item["answer_segments"] and packet["persona_answer"]
    assert all(s and s in packet["persona_answer"] for s in item["answer_segments"])
    return " ".join(item["answer_segments"])


def followup():
    validate();raw=read(RAW);packets={p["id"]:p for p in read(ROOT/"eval/scoped_reply_packet.json")}
    replies={r["id"]:r for r in read(REPLIES)}
    assert set(replies)==set(packets)
    frozen=ROOT/"eval/scoped_reply_freeze.json"
    evidence={"packet_sha256":sha(ROOT/"eval/scoped_reply_packet.json"),"review_sha256":sha(REPLIES)}
    if frozen.exists(): assert read(frozen)==evidence
    else: write_json(frozen,evidence)
    for n,(cid,p) in enumerate(packets.items()):
        answer=checked_answer(replies[cid],p)
        context=raw[cid]["first"]["payload"]["clarification_context"]
        if answer is None:
            fn=lambda:{"status":"simulated_answer_unavailable","result":[]}
        else:
            fn=lambda p=p,context=context,answer=answer:followup_call(p["original_question"],context,answer)
        execute(raw,cid,"followup",fn)
        if (n+1)%10==0: print(f"Completed follow-ups {n+1}/{len(packets)}",flush=True)


def ratio(n,d): return {"n":n,"d":d,"percent":round(n/d*100,2) if d else None}


def latency(xs):
    available=sorted(x for x in xs if x is not None)
    return {"count":len(available),"missing":len(xs)-len(available),
            "mean_s":round(statistics.mean(available),3) if available else None,
            "p50_s":round(statistics.median(available),3) if available else None,
            "p95_s":round(available[max(0, __import__('math').ceil(.95*len(available))-1)],3) if available else None}


def summarize():
    validate();cases=read(DATA);raw=read(RAW)
    replies={r["id"]:r for r in read(REPLIES)}
    assert len(raw)==120
    rows=[];decisions=Counter();paired=Counter();usage={"baseline":[],"final":[]}
    for c in cases:
        r=raw[c["id"]];b=r["baseline"]["payload"];f=r["first"]["payload"]
        trigger=f["status"]=="needs_clarification"
        assert not trigger or "followup" in r
        end=r.get("followup",r["first"])["payload"]
        bcorrect=b["status"]=="success" and compare(c["ground_truth_result"],b.get("result",[]),c["ordered"])
        correct=end["status"]=="success" and compare(c["ground_truth_result"],end.get("result",[]),c["ordered"])
        decision=f.get("gate_decision",{}).get("decision",f["status"])
        decisions[("ambiguous" if c["should_clarify"] else "clear",decision)]+=1
        review=replies.get(c["id"],{})
        interaction=end.get("interaction",{})
        resolved=interaction.get("resolved_slots",[])
        used=(trigger and review.get("valid_question",False) and bool(resolved)
              and interaction.get("original_question")==c["question"]
              and interaction.get("clarification_answer")==" ".join(review.get("answer_segments",[]))
              and interaction.get("known_constraints")==f.get("clarification_context",{}).get("known_constraints")
              and all(x["quote"] in interaction.get("clarification_answer","") for x in resolved)
              and all(x["quote"] in end.get("engine_input","") for x in resolved))
        strict=correct and ((not c["should_clarify"] and not trigger) or (c["should_clarify"] and used))
        pair=("both_right" if bcorrect and correct else "baseline_wrong_final_right" if correct else
              "baseline_right_final_wrong" if bcorrect else "both_wrong")
        paired[pair]+=1
        firsttime=r["first"]["elapsed_s"];followtime=r.get("followup",{}).get("elapsed_s",0)
        total=None if firsttime is None or followtime is None else firsttime+followtime
        usage["baseline"].extend(r["baseline"]["usage"])
        usage["final"].extend(r["first"]["usage"]+r.get("followup",{}).get("usage",[]))
        rows.append({"id":c["id"],"question":c["question"],"ambiguous":c["should_clarify"],
            "missing_slot":c["missing_slot"],"decision":decision,"triggered":trigger,
            "valid_question":review.get("valid_question",False),"answer_used":bool(used),
            "baseline_correct":bcorrect,"final_correct":correct,"strict_success":bool(strict),"pair":pair,
            "baseline_latency_s":r["baseline"]["elapsed_s"],"first_latency_s":firsttime,"total_latency_s":total,
            "baseline_sql":b.get("sql",""),"final_sql":end.get("sql",""),
            "baseline_result":b.get("result",[]),"final_result":end.get("result",[]),
            "ground_truth_result":c["ground_truth_result"],"final_status":end["status"]})
    tp=sum(r["ambiguous"] and r["triggered"] for r in rows)
    fp=sum(not r["ambiguous"] and r["triggered"] for r in rows)
    tn=sum(not r["ambiguous"] and r["decision"]=="proceed" for r in rows)
    fn=60-tp
    metrics={"decision_accuracy":ratio(tp+tn,120),"precision":ratio(tp,tp+fp),"recall":ratio(tp,60),
        "f1":ratio(2*tp,2*tp+fp+fn),"unnecessary":ratio(fp,60),"missed":ratio(fn,60),
        "decision_counts":[{"label":k[0],"decision":k[1],"count":v} for k,v in decisions.items()],
        "paired":dict(paired),"baseline":{},"final":{}}
    for name,key in [("baseline","baseline_correct"),("final","final_correct")]:
        for label,subset in [("overall",rows),("clear",[r for r in rows if not r["ambiguous"]]),("ambiguous",[r for r in rows if r["ambiguous"]])]:
            metrics[name][label]=ratio(sum(r[key] for r in subset),len(subset))
        metrics[name]["latency"]=latency([r["baseline_latency_s" if name=="baseline" else "total_latency_s"] for r in rows])
        records=usage[name]
        metrics[name]["usage"]={"calls":len(records),"mean_calls":round(len(records)/120,3),
            "input_tokens":sum(x["input_tokens"] or 0 for x in records),"output_tokens":sum(x["output_tokens"] or 0 for x in records),
            "missing_usage_calls":sum(x["input_tokens"] is None or x["output_tokens"] is None for x in records)}
    metrics["final"]["first_latency"]=latency([r["first_latency_s"] for r in rows])
    metrics["final"]["strict_overall"]=ratio(sum(r["strict_success"] for r in rows),120)
    metrics["final"]["strict_ambiguous"]=ratio(sum(r["strict_success"] and r["ambiguous"] for r in rows),60)
    subset=[r for r in rows if r["ambiguous"] and r["answer_used"]]
    metrics["final"]["accepted_answer_subset"]=ratio(sum(r["final_correct"] for r in subset),len(subset))
    write_json(ROOT/"eval/scoped_clarification_per_case.json",rows)
    write_json(ROOT/"eval/scoped_clarification_report.json",metrics)
    write_json(ROOT/"eval/scoped_clarification_bad_cases.json",[r for r in rows if not r["strict_success"] or not r["baseline_correct"]])
    print(json.dumps(metrics,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=["first","followup","summarize"])
    args=parser.parse_args()
    with (ROOT/".run/scoped_evaluation.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        {"first":first,"followup":followup,"summarize":summarize}[args.phase]()
