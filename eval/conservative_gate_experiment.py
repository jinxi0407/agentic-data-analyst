"""Gate-only development evidence; never overwrites the released regression."""

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import fcntl
import json
from pathlib import Path
import time
from unittest.mock import patch

from app.tools import qwen

from app.agent.entity_context import entity_context
from app.tools.database import fetch_all
from eval import run_300_clarification_regression as original
from eval.scoring import fingerprint, write_json

ROOT = original.ROOT
PREFIX = ROOT / "eval/conservative_gate_dev_transport_fix"
WORKERS = 1


def verify_engine():
    frozen = original.read(original.FREEZE)
    protected = {k: v for k, v in frozen['tracked_blobs'].items()
                 if k.startswith(('app/', 'ui/')) or k in
                 ('eval/strong_baseline.py', 'eval/strong_baseline_v2.py', 'eval/scoring.py')}
    protected.pop('app/agent/scoped_clarification.py')
    protected.pop('app/tools/qwen.py')
    original.verify_files(protected)
    # Timeout passthrough is opt-in. Existing engine calls must remain identical.
    old_wrapper = original.git('show', original.BASE + ':app/tools/qwen.py')
    current_wrapper = (ROOT / 'app/tools/qwen.py').read_text()
    old_nodes = {n.name: ast.dump(n) for n in ast.parse(old_wrapper).body if isinstance(n,ast.FunctionDef)}
    new_nodes = {n.name: ast.dump(n) for n in ast.parse(current_wrapper).body if isinstance(n,ast.FunctionDef)}
    assert all(new_nodes[k] == v for k,v in old_nodes.items() if k != 'generate_text')
    before = next(n for n in ast.parse(old_wrapper).body if isinstance(n,ast.FunctionDef) and n.name=='generate_text')
    after = next(n for n in ast.parse(current_wrapper).body if isinstance(n,ast.FunctionDef) and n.name=='generate_text')
    assert [a.arg for a in after.args.kwonlyargs] == ['request_timeout']
    assert ast.dump(after.args.kw_defaults[0]) == ast.dump(ast.Constant(None))
    after.args.kwonlyargs, after.args.kw_defaults = [], []
    addition = ast.parse("if request_timeout is not None:\n    kwargs['request_timeout'] = request_timeout").body[0]
    matches = [n for n in after.body if ast.dump(n)==ast.dump(addition)]
    assert len(matches) == 1
    after.body.remove(matches[0])
    assert ast.dump(before) == ast.dump(after), 'Unapproved shared wrapper change'
    old = original.git('show', original.BASE + ':app/agent/scoped_clarification.py')
    now = (ROOT / 'app/agent/scoped_clarification.py').read_text()
    def direct(source):
        return ast.dump(next(n for n in ast.parse(source).body
                             if isinstance(n, ast.FunctionDef) and n.name == 'direct'))
    assert direct(old) == direct(now), 'Production direct path changed'
    assert original.sha(original.DATA) == frozen['cases_file_sha256']
    assert original.sha(original.MANIFEST) == frozen['manifest_sha256']
    assert fingerprint(fetch_all) == frozen['database']
    return frozen


def audit():
    path = ROOT / 'eval/conservative_gate_122_audit.json'
    assert not path.exists(), 'Preserve existing audit'
    # Offline reviewer annotations, not runtime question rules.
    groups = [
        ('A', [86, 186], '优惠率未在当前生产契约中定义；优惠/原价与优惠/实付会产生不同结果。186的反问虽然问错时间，但问题本身仍有未定义的比例口径。'),
        ('C', [50], 'Gate提出2026-02-29这个不存在的日期。原问题的2026年2月本可按自然月处理。'),
        ('C', [138], 'Gate给出两个相同的日期区间却称为不同解释，属于输出证据错误。'),
        ('C', [197, 206], 'Gate把最近231天换算为错误的起始日期；原问题可按现有DATE_SUB规则处理。'),
        ('B', [3,100,208,115,275], '商品目录上下文支持按原文品牌字面值过滤；不应强行改问城市或换实体。数据库无匹配也是合法空结果；最近上架Top-K指定了排序而非额外时间窗口。'),
        ('B', [2,80,258,273], '已明确年月和上/下半月，通常日历含义可确定边界；未表达自定义账期，不应制造15/16日之争。'),
        ('B', [4,44,97,118,135,224,294], '最近上架前K已通过launch_date指定排序和所返回指标；不应再索要额外最近N天或换成销量。'),
        ('B', [5,10,57,59,78,85,147,256], '最近一次注册日期是register_date的最大值，不是缺少滚动时间窗口。'),
        ('B', [7,58,170,181,226], '在售商品目录中的价格由list_price显示价格语义确定；成本价或交易行价格不是同一请求的合理替代。'),
        ('B', [18,183,200,227,242,245,267], '平均商品标价毛利率指按商品的标价减成本占标价再求平均；成本利润率或整体加权口径不是原文要求。此判断基于通常指标含义，不宣称生产字典显式定义了该指标。'),
        ('B', [60,134,141,210,234,270,288], '单件标价毛利明确指list_price-cost_price；仅问是否如此并未证明关键slot缺失。'),
        ('B', [68,163], '商品总数、is_active在售数及两者比例已由商品粒度和schema确定；无须重复确认。'),
        ('B', [93,172], '标价成本倍数已用文字指定list_price/cost_price，不是缺失指标。'),
        ('B', [92,121,139,144], '全部订单状态与支付方式限定订单粒度，优惠占原始金额明确discount_amount/gross_amount；无需改问商品明细粒度。'),
        ('B', [113,124,199,249,262], '按用户累计有效订单优惠属于订单粒度，orders.discount_amount由schema确定；不应任意切换到商品明细。'),
        ('B', [159,160,162,189], '已有时间、分组与成交口径；成交金额按订单paid_amount、成交单数按有效订单，不能把业务契约当成待确认项。'),
        ('B', [87,235], '已明确自然月或年底截止点，日历边界可确定，不需要重新索要起止日期。'),
    ]
    labels = {}
    for label, ids, reason in groups:
        for n in ids:
            assert n not in labels
            labels[n] = (label, reason)
    events = [json.loads(x) for x in original.RAW.read_text().splitlines()]
    rows = []
    for r in events:
        if r['state'] != 'complete' or r['mode'] != 'on':
            continue
        p = r['payload']
        if p.get('status') != 'needs_clarification':
            continue
        n = int(r['id'].rsplit('_', 1)[1])
        if n not in labels:
            assert p['gate_decision']['missing_slots'] == ['time'], r['id']
            label, reason = 'B', '问题已给出最近N天或近半年及参考日，可按现有DATE_SUB日/月规则处理；不应另造营业日、订单活跃日或完整自然月解释。'
        else:
            label, reason = labels[n]
        rows.append({'case_id': r['id'], 'question': p['question'],
                     'gate_output': p['gate_decision'], 'classification': label,
                     'reason': reason})
    assert len(rows) == 122 and set(labels) <= {int(r['case_id'].rsplit('_',1)[1]) for r in rows}
    counts = dict(Counter(r['classification'] for r in rows))
    write_json(path, {'counts': counts, 'review': 'Offline human-style contract review, no new LLM calls, no Ground Truth used to decide ambiguity. C is output evidence failure; these four original cases themselves are resolvable. Classification is reviewer judgment, not new frozen labels.',
        'separate_non_trigger_errors': {'invalid_output': 37, 'needs_rephrase': 3},
        'source_sha256': original.sha(original.RAW), 'cases': sorted(rows, key=lambda x:x['case_id'])})
    print(counts)


def development():
    frozen = verify_engine()
    for name in ('app/agent/scoped_clarification.py','app/tools/qwen.py'):
        assert (ROOT/name).read_text() == original.git('show','8fb1e3a:'+name) + '\n'
    current_config = original.public_config()
    for key in ('chat_model','embedding_model','sql_temperature','execution_retry_limit',
                'sql_max_rows','sdk_version','sdk_default_timeout_seconds'):
        assert current_config[key] == frozen['config'][key], f'OFF configuration changed: {key}'
    cases = original.read(original.DATA)
    old = {r['id']:r for r in original.read(Path(str(original.PREFIX)+'_per_case.json'))}
    saved = original.records()
    for case in cases:
        assert old[case['id']]['question'] == case['question']
        assert old[case['id']]['ground_truth_result'] == case['ground_truth_result']
        assert original.score(case,saved[(case['id'],'off')]) == old[case['id']]['off']
    assert sum(r['off']['correct'] for r in old.values()) == 232
    freeze_path = Path(str(PREFIX) + '_freeze.json')
    record_path = Path(str(PREFIX) + '_events.jsonl')
    public = original.public_config()
    public.update(workers_per_mode=WORKERS,batch_size=WORKERS,
                  schedule='Fresh ON serial only; historical OFF is development diagnostic reference',
                  timeout_policy='Gate connect/read 5/30 seconds; SQL engine retains SDK defaults',
                  gate_request_timeout_seconds=[5,30], gate_response_format='json_object')
    config = {'gate_sha256': original.sha(ROOT / 'app/agent/scoped_clarification.py'),
              'qwen_wrapper_sha256': original.sha(ROOT / 'app/tools/qwen.py'),
              'runner_sha256': original.sha(Path(__file__)), 'database': frozen['database'],
              'cases_sha256': frozen['cases_file_sha256'], 'config': public,
              'off_source_sha256':original.sha(original.RAW),
              'off_reuse_note':'Original OFF re-scored unchanged: 232/300. Same SQL inputs, engine, model parameters, scorer and database. Historical OFF used four workers; current ON is serial, so latency is descriptive, not a controlled concurrency comparison.',
              'purpose': 'Revealed development regression. Fresh ON, historical unchanged-engine OFF retained only as diagnostic paired reference.'}
    if freeze_path.exists():
        assert original.read(freeze_path) == config
    else:
        assert not record_path.exists()
        write_json(freeze_path, config)
    records = {}
    if record_path.exists():
        for line in record_path.read_text().splitlines():
            r = json.loads(line)
            assert records.get(r['id'], {}).get('state') != 'complete'
            records[r['id']] = r
    if any(r['state'] != 'complete' for r in records.values()):
        raise RuntimeError('Uncertain started calls; inspect before any resume. Never duplicate API calls.')
    if any(r.get('failures') for r in records.values()):
        raise RuntimeError('Previously recorded infrastructure failure; do not auto-resume')
    entity_context()
    def append(r):
        with record_path.open('a') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            import os
            os.fsync(f.fileno())
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for offset in range(0,300,WORKERS):
            pending = {}
            for c in cases[offset:offset+WORKERS]:
                if c['id'] in records:
                    continue
                append({'id': c['id'], 'state': 'started', 'time': time.time()})
                pending[pool.submit(measured_on, c['question'], date.fromisoformat(c['reference_date']))] = c['id']
            for future in as_completed(pending):
                r = {'id': pending[future], **future.result()}
                append(r)
                records[r['id']] = r
                if r['failures'] or r['payload'].get('status') == 'system_error':
                    summarize(cases,records,old)
                    print(json.dumps({'halted':True,'case_id':r['id'],'elapsed_s':r['elapsed_s'],
                                      'failures':r['failures'],'status':r['payload'].get('status')},ensure_ascii=False),flush=True)
                    return
            if offset % 20 == 0:
                print(f'Development ON persisted {len(records)}/300', flush=True)
    verify_engine()
    summarize(cases,records,old)


def measured_on(question, reference):
    sdk = qwen._require_dashscope()
    call = sdk.Generation.call
    failures = []
    def observe(**kwargs):
        stage = 'gate' if kwargs.get('response_format') else 'sql_generation'
        started = time.perf_counter()
        try:
            response = call(**kwargs)
        except Exception as exc:
            failures.append({'stage':stage,'error_type':type(exc).__name__,
                             'elapsed_s':round(time.perf_counter()-started,6)})
            raise
        if response.status_code != 200:
            failures.append({'stage':stage,'error_type':'api_error',
                             'http_status':response.status_code,'api_code':response.get('code'),
                             'elapsed_s':round(time.perf_counter()-started,6)})
        return response
    with patch.object(sdk.Generation,'call',observe):
        result = original.measured_call(question,reference,'on')
    result['failures'] = failures
    return result


def paired_label(off,on):
    if off['correct']:
        if on['correct']:
            return 'off_correct_on_correct'
        return 'off_correct_on_wrong' if on['first_turn_completed'] else 'off_correct_on_incomplete'
    return 'off_wrong_on_correct' if on['correct'] else 'off_wrong_on_wrong_or_incomplete'


def summarize(cases,records,old):
    rows = [{'id':c['id'], 'question':c['question'], 'off':old[c['id']]['off'],
             'old_on':old[c['id']]['on'], 'on':original.score(c, records[c['id']])} for c in cases
            if c['id'] in records and records[c['id']]['state']=='complete']
    for row in rows:
        row['pair'] = paired_label(row['off'],row['on'])
    complete = len(rows)==300
    failures = [{'case_id':r['id'],'elapsed_s':r['elapsed_s'],'failures':r.get('failures',[]),
                 'status':r['payload'].get('status')} for r in records.values()
                if r.get('failures') or r.get('payload',{}).get('status')=='system_error']
    trigger = sum(r['on']['triggered'] for r in rows)
    correct = sum(r['on']['correct'] for r in rows)
    stats = {'n':300, 'completed':len(rows),'complete':complete,
             'trigger_count':trigger,'trigger_rate':original.ratio(trigger,300) if complete else None,
             'first_turn_accuracy':original.ratio(correct,300) if complete else None,
             'correct':sum(r['on']['correct'] for r in rows),
             'off_correct_on_incomplete':sum(r['off']['correct'] and not r['on']['first_turn_completed'] for r in rows),
             'off_correct_on_wrong_or_incomplete':sum(r['off']['correct'] and not r['on']['correct'] for r in rows),
             'status_counts':dict(Counter(r['on']['status'] for r in rows)),
             'old_trigger_count':122, 'old_off_correct_on_incomplete':130,
             'paired':dict(Counter(r['pair'] for r in rows)),
             'average_model_calls':sum(r['on']['model_calls'] for r in rows)/len(rows) if rows else None,
             'infrastructure_failure_count':len(failures),'failures':failures,
             'off_reused':True,'off_accuracy':original.ratio(232,300),
             'no_user_answers':True,
             'latency':original.latency([r['on']['elapsed_s'] for r in rows])}
    write_json(Path(str(PREFIX)+'_per_case.json'), rows)
    write_json(Path(str(PREFIX)+'_report.json'), stats)
    print(json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['audit','development','verify'])
    args = p.parse_args()
    with (ROOT / '.run/conservative_gate_eval.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        {'audit':audit, 'development':development, 'verify':verify_engine}[args.action]()
