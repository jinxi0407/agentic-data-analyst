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

from app.agent.entity_context import entity_context
from app.tools.database import fetch_all
from eval import run_300_clarification_regression as original
from eval.scoring import fingerprint, write_json

ROOT = original.ROOT
PREFIX = ROOT / "eval/conservative_gate_dev_round2"


def verify_engine():
    frozen = original.read(original.FREEZE)
    protected = {k: v for k, v in frozen['tracked_blobs'].items()
                 if k.startswith(('app/', 'ui/')) or k in
                 ('eval/strong_baseline.py', 'eval/strong_baseline_v2.py', 'eval/scoring.py')}
    protected.pop('app/agent/scoped_clarification.py')
    original.verify_files(protected)
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
    freeze_path = Path(str(PREFIX) + '_freeze.json')
    record_path = Path(str(PREFIX) + '_events.jsonl')
    config = {'gate_sha256': original.sha(ROOT / 'app/agent/scoped_clarification.py'),
              'runner_sha256': original.sha(Path(__file__)), 'database': frozen['database'],
              'cases_sha256': frozen['cases_file_sha256'], 'config': original.public_config(),
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
    cases = original.read(original.DATA)
    entity_context()
    def append(r):
        with record_path.open('a') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            import os
            os.fsync(f.fileno())
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0,300,4):
            pending = {}
            for c in cases[offset:offset+4]:
                if c['id'] in records:
                    continue
                append({'id': c['id'], 'state': 'started', 'time': time.time()})
                pending[pool.submit(original.measured_call, c['question'], date.fromisoformat(c['reference_date']), 'on')] = c['id']
            for future in as_completed(pending):
                r = {'id': pending[future], **future.result()}
                append(r)
                records[r['id']] = r
            if offset % 20 == 0:
                print(f'Development ON persisted {len(records)}/300', flush=True)
    verify_engine()
    old = {r['id']: r for r in original.read(Path(str(original.PREFIX)+'_per_case.json'))}
    rows = [{'id':c['id'], 'question':c['question'], 'off':old[c['id']]['off'],
             'old_on':old[c['id']]['on'], 'on':original.score(c, records[c['id']])} for c in cases]
    stats = {'n':300, 'trigger_count':sum(r['on']['triggered'] for r in rows),
             'correct':sum(r['on']['correct'] for r in rows),
             'off_correct_on_incomplete':sum(r['off']['correct'] and not r['on']['first_turn_completed'] for r in rows),
             'off_correct_on_wrong_or_incomplete':sum(r['off']['correct'] and not r['on']['correct'] for r in rows),
             'status_counts':dict(Counter(r['on']['status'] for r in rows)),
             'old_trigger_count':122, 'old_off_correct_on_incomplete':130,
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
