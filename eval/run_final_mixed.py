"""One-shot, serial interactive evaluation. Oracle artifacts stay outside candidate calls."""

import argparse
from collections import Counter
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

from app.agent import scoped_clarification as gate
from app.agent.entity_context import entity_context
from app.tools import qwen
from app.tools.database import fetch_all
from eval import run_300_clarification_regression as shared
from eval.scoring import compare, fingerprint, write_json

ROOT = shared.ROOT
DATA = ROOT/'eval/final_mixed_cases.json'
FREEZE = ROOT/'eval/final_mixed_freeze.json'
EVENTS = ROOT/'eval/final_mixed_events.jsonl'
PACKET = ROOT/'eval/final_mixed_reply_packet.json'
REVIEWS = ROOT/'eval/final_mixed_reply_review.json'


def validate():
    f = shared.read(FREEZE)
    for name,h in f['hashes'].items():
        assert shared.sha(ROOT/name)==h, f'Frozen artifact changed: {name}'
    assert fingerprint(fetch_all)==f['database']
    p = shared.public_config()
    for key in ('chat_model','embedding_model','sql_temperature','gate_temperature',
                'execution_retry_limit','gate_format_retry_limit','sql_max_rows','sdk_version'):
        assert p[key]==f['model_config'][key], f'Model configuration changed: {key}'
    assert f['workers']==1 and f['semantic_review_complete'] and f['novelty_review_complete']
    cases = shared.read(DATA)
    assert len(cases)==200 and Counter(c['kind'] for c in cases)=={
        'clear':140,'time':20,'metric':20,'entity_filter':20}
    return f,cases


def candidate(question,reference,mode):
    if mode=='off':
        return gate.direct(question,reference)
    if mode=='on':
        return gate.run_interactive(question,reference_date=reference)
    raise ValueError('Unknown mode')


def followup_candidate(question,context,answer):
    return gate.run_interactive(question,answer,gate.Context.model_validate(context))


def measured(fn):
    sdk = qwen._require_dashscope()
    original = sdk.Generation.call
    failures = []
    def observe(**kwargs):
        started = time.perf_counter()
        stage = 'gate' if kwargs.get('response_format') else 'sql_generation'
        try:
            result = original(**kwargs)
        except Exception as exc:
            failures.append({'stage':stage,'error_type':type(exc).__name__,
                             'elapsed_s':round(time.perf_counter()-started,6)})
            raise
        if result.status_code!=200:
            failures.append({'stage':stage,'error_type':'api_error','http_status':result.status_code,
                             'api_code':result.get('code'),'elapsed_s':round(time.perf_counter()-started,6)})
        return result
    started = time.perf_counter()
    with patch.object(sdk.Generation,'call',observe), qwen.capture_usage() as usage:
        try:
            payload = fn()
        except Exception as exc:
            payload = {'status':'system_error','result':[],'error':type(exc).__name__}
    return {'state':'complete','payload':shared.clean(payload),'usage':usage,'failures':failures,
            'elapsed_s':round(time.perf_counter()-started,6)}


def append(event):
    with EVENTS.open('a') as f:
        f.write(json.dumps(event,ensure_ascii=False)+'\n')
        f.flush()
        os.fsync(f.fileno())


def records():
    rows = {}
    if EVENTS.exists():
        for line in EVENTS.read_text().splitlines():
            e = json.loads(line)
            key = (e['id'],e['stage'])
            assert rows.get(key,{}).get('state')!='complete', 'Duplicate completed stage'
            rows[key]=e
    assert all(e['state']=='complete' for e in rows.values()), 'Unobserved in-flight call; do not repeat'
    return rows


def execute(rows,cid,stage,fn):
    key = (cid,stage)
    if key in rows:
        return
    append({'id':cid,'stage':stage,'state':'started','started_unix':time.time()})
    event = {'id':cid,'stage':stage,**measured(fn)}
    append(event)
    rows[key]=event
    if event['failures'] or event['payload'].get('status')=='system_error':
        write_json(ROOT/'eval/final_mixed_halt.json',{'id':cid,'stage':stage,
            'elapsed_s':event['elapsed_s'],'failures':event['failures'],'status':event['payload'].get('status')})
        raise RuntimeError(f'Infrastructure failure at {cid}/{stage}; stopped without rerun')


def answer_packet(case,payload):
    assert payload['status']=='needs_clarification'
    slots = payload.get('clarification_context',{}).get('missing_slots',[])
    eligible = case['answer_slot']!='none' and bool(case['simulated_answer'])
    # Review input deliberately omits SQL, Ground Truth and intended full meaning.
    return {'id':case['id'],'original_question':case['question'],
            'actual_question':payload['clarification_question'],'asked_slots':slots,
            'slot_eligible':eligible,'exact_slot_match':slots==[case['answer_slot']],
            'frozen_answer':case['simulated_answer'] if eligible else ''}


def first():
    f,cases = validate()
    rows = records()
    assert not any(e.get('failures') for e in rows.values()), 'Previous infrastructure halt'
    runfreeze = ROOT/'eval/final_mixed_run_freeze.json'
    if not runfreeze.exists():
        assert not rows
        commit = shared.git('rev-parse','HEAD')
        tracked = shared.git('show',commit+':eval/final_mixed_cases.json')
        assert json.loads(tracked)==cases, 'Dataset must be locally committed before candidate calls'
        write_json(runfreeze,{'data_commit':commit,'manifest_sha256':shared.sha(FREEZE),
            'gate_freeze_commit':f['gate_freeze_commit'],'created_unix':time.time()})
    assert shared.read(runfreeze)['manifest_sha256']==shared.sha(FREEZE)
    entity_context()
    reference = date.fromisoformat(f['reference_date'])
    for i,c in enumerate(cases):
        for mode in (('off','on') if i%2==0 else ('on','off')):
            execute(rows,c['id'],mode,lambda c=c,mode=mode:candidate(c['question'],reference,mode))
        if (i+1)%10==0:
            print(f'Fresh paired first turns {i+1}/200',flush=True)
    validate()
    packets = [answer_packet(c,rows[(c['id'],'on')]['payload']) for c in cases
               if rows[(c['id'],'on')]['payload']['status']=='needs_clarification']
    write_json(PACKET,packets)
    print(f'Local answer eligibility review required: {len(packets)} questions',flush=True)


def checked_answer(review,packet):
    assert review['id']==packet['id'] and review['actual_question']==packet['actual_question']
    assert review['reason'].strip()
    if not review['answerable']:
        return None
    assert packet['slot_eligible'] and packet['frozen_answer']
    return packet['frozen_answer']


def followup():
    validate()
    rows = records()
    assert not any(e.get('failures') for e in rows.values()), 'Previous infrastructure halt'
    packets = shared.read(PACKET)
    reviews = {r['id']:r for r in shared.read(REVIEWS)}
    assert len(reviews)==len(packets) and set(reviews)=={p['id'] for p in packets}
    path = ROOT/'eval/final_mixed_reply_freeze.json'
    hashes = {'packet':shared.sha(PACKET),'review':shared.sha(REVIEWS)}
    if path.exists():
        assert shared.read(path)==hashes
    else:
        write_json(path,hashes)
    for i,p in enumerate(packets):
        answer = checked_answer(reviews[p['id']],p)
        if answer is None:
            key = (p['id'],'followup')
            if key not in rows:
                record = {'id':p['id'],'stage':'followup','state':'complete',
                    'payload':{'status':'simulated_answer_unavailable','result':[]},
                    'usage':[],'failures':[],'elapsed_s':0}
                append(record)
                rows[key]=record
            continue
        context = rows[(p['id'],'on')]['payload']['clarification_context']
        execute(rows,p['id'],'followup',lambda p=p,context=context,answer=answer:
            followup_candidate(p['original_question'],context,answer))
        if (i+1)%10==0:
            print(f'Single-slot follow-ups {i+1}/{len(packets)}',flush=True)
    validate()


def summarize():
    f,cases = validate()
    raw = records()
    reviews = {r['id']:r for r in shared.read(REVIEWS)}
    rows=[]
    for c in cases:
        off,on = (raw[(c['id'],mode)] for mode in ('off','on'))
        first = on['payload']
        trigger = first.get('status')=='needs_clarification'
        follow = raw.get((c['id'],'followup'))
        assert not trigger or follow is not None
        end = (follow or on)['payload']
        b = off['payload'].get('status')=='success' and compare(c['ground_truth_result'],off['payload'].get('result',[]),c['ordered'])
        a = end.get('status')=='success' and compare(c['ground_truth_result'],end.get('result',[]),c['ordered'])
        interaction = end.get('interaction',{})
        resolved = interaction.get('resolved_slots',[])
        used = (trigger and reviews.get(c['id'],{}).get('answerable',False) and bool(resolved)
            and interaction.get('original_question')==c['question']
            and interaction.get('clarification_answer')==c['simulated_answer']
            and interaction.get('known_constraints',[])==first.get('clarification_context',{}).get('known_constraints',[])
            and all(x['slot'] in first.get('clarification_context',{}).get('missing_slots',[])
                    and x['quote'] in c['simulated_answer']
                    and x['quote'] in end.get('engine_input','') for x in resolved))
        rows.append({'id':c['id'],'kind':c['kind'],'question':c['question'],'triggered':trigger,
            'decision':first.get('gate_decision',{}).get('decision',first.get('status')),
            'off_correct':bool(b),'on_correct':bool(a),'answer_used':bool(used),
            'strict_ambiguous_success':bool(c['kind']!='clear' and used and a),
            'pair':f'off_{"correct" if b else "wrong"}_on_{"correct" if a else "wrong"}',
            'off_status':off['payload'].get('status'),'on_status':end.get('status'),
            'off_latency_s':off['elapsed_s'],'on_latency_s':on['elapsed_s']+(follow['elapsed_s'] if follow else 0),
            'off_calls':len(off['usage']),'on_calls':len(on['usage'])+(len(follow['usage']) if follow else 0),
            'off_sql':off['payload'].get('sql',''),'on_sql':end.get('sql',''),
            'off_result':off['payload'].get('result',[]),'on_result':end.get('result',[]),
            'ground_truth_result':c['ground_truth_result']})
    tp=sum(r['kind']!='clear' and r['triggered'] for r in rows)
    fp=sum(r['kind']=='clear' and r['triggered'] for r in rows)
    tn=sum(r['kind']=='clear' and r['decision']=='proceed' for r in rows)
    metrics={'total':200,'clear':140,'ambiguous':60,'off':{},'on':{},
        'clarification_accuracy':shared.ratio(tp+tn,200),'precision':shared.ratio(tp,tp+fp),
        'recall':shared.ratio(tp,60),'f1':shared.ratio(2*tp,2*tp+fp+60-tp),
        'unnecessary':shared.ratio(fp,140),'missed':shared.ratio(60-tp,60),
        'strict_ambiguous_success':shared.ratio(sum(r['strict_ambiguous_success'] for r in rows),60),
        'paired':dict(Counter(r['pair'] for r in rows)),
        'decision_counts':dict(Counter(r['decision'] for r in rows)),
        'infrastructure_failures':sum(bool(x.get('failures')) for x in raw.values())}
    for mode in ('off','on'):
        for label,subset in [('overall',rows),('clear',[r for r in rows if r['kind']=='clear']),
                             ('ambiguous',[r for r in rows if r['kind']!='clear'])]:
            metrics[mode][label]=shared.ratio(sum(r[mode+'_correct'] for r in subset),len(subset))
        metrics[mode]['latency']=shared.latency([r[mode+'_latency_s'] for r in rows])
        metrics[mode]['average_model_calls']=sum(r[mode+'_calls'] for r in rows)/200
    metrics['delta_pp']=round((sum(r['on_correct'] for r in rows)-sum(r['off_correct'] for r in rows))/2,2)
    write_json(ROOT/'eval/final_mixed_per_case.json',rows)
    write_json(ROOT/'eval/final_mixed_report.json',metrics)
    write_json(ROOT/'eval/final_mixed_bad_cases.json',[r for r in rows if not r['off_correct'] or not r['on_correct']
        or (r['kind']!='clear' and not r['strict_ambiguous_success']) or (r['kind']=='clear' and r['triggered'])])
    print(json.dumps(metrics,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('phase',choices=['first','followup','summarize'])
    args=p.parse_args()
    with (ROOT/'.run/final_mixed.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        {'first':first,'followup':followup,'summarize':summarize}[args.phase]()
