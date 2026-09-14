"""Paired first-turn regression of the frozen v1.1.0, without user answers."""

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date
import fcntl
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
from unittest.mock import patch

from app.agent import scoped_clarification as scoped
from app.agent.entity_context import entity_context
from app.config import settings
from app.tools.database import fetch_all
from app.tools.qwen import capture_usage
from eval.scoring import compare, digest, fingerprint, write_json
from eval.strong_baseline import MAX_RETRY, SQL_TEMPERATURE

ROOT = Path(__file__).resolve().parents[1]
BASE = "2dc294fe43dc64658af7c85e7b60aae59a6be6a8"
DATA = ROOT / "eval/final_release_holdout_300.json"
MANIFEST = ROOT / "eval/final_release_manifest.json"
PREFIX = ROOT / "eval/clarification_300_regression"
FREEZE = Path(str(PREFIX) + "_freeze.json")
RAW = Path(str(PREFIX) + "_events.jsonl")
REPORT = ROOT / "FINAL_300_CLARIFICATION_REGRESSION.md"
WORKERS = 4
BATCH = 20


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["/usr/bin/git", *args], cwd=ROOT,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).decode().strip()


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        for secret in (settings.dashscope_api_key, settings.mysql_password,
                       settings.mysql_root_password):
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
                      "[REDACTED]", value)
    return value


def public_config():
    from dashscope.common.constants import DEFAULT_REQUEST_TIMEOUT_SECONDS
    return {"chat_model": settings.qwen_chat_model,
        "embedding_model": settings.qwen_embedding_model,
        "sql_temperature": SQL_TEMPERATURE, "gate_temperature": 0,
        "execution_retry_limit": MAX_RETRY, "gate_format_retry_limit": 1,
        "sql_max_rows": settings.sql_max_rows, "workers_per_mode": WORKERS,
        "batch_size": BATCH, "sdk_version": version("dashscope"),
        "sdk_default_timeout_seconds": DEFAULT_REQUEST_TIMEOUT_SECONDS,
        "timeout_policy": "Unmodified SDK defaults for both modes; no outer timeout or evaluation retry",
        "model_calls_definition": "Calls recorded by existing capture_usage, including API/transport errors; internal SDK wire retries are not separately counted",
        "schedule": "Original case order, batches of 20; OFF then ON in even batches, ON then OFF in odd batches; same shared 4-worker pool",
        "second_user_turn": False, "embedding_calls": 0}


def verify_files(blobs):
    for name, expected in blobs.items():
        data = (ROOT / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Frozen tracked file changed: {name}")


def prepare():
    if FREEZE.exists() or RAW.exists():
        raise RuntimeError("Existing experiment found; do not replace freeze or records")
    assert git("rev-parse", "HEAD") == BASE == git("rev-parse", "v1.1.0^{commit}")
    cases, manifest = read(DATA), read(MANIFEST)
    assert len(cases) == len({c['id'] for c in cases}) == 300
    assert digest(cases) == manifest['cases_sha256']
    assert all(c['reference_date'] == manifest['reference_date'] for c in cases)
    assert fingerprint(fetch_all) == manifest['database'], "Database snapshot changed"
    assert settings.qwen_chat_model == 'qwen-plus'
    assert settings.qwen_embedding_model == 'text-embedding-v4'
    blobs = {}
    for row in git('ls-tree', '-r', '-z', BASE).split('\0'):
        if not row:
            continue
        meta, name = row.split('\t', 1)
        assert meta.split()[1] == 'blob'
        blobs[name] = meta.split()[2]
    verify_files(blobs)
    config = public_config()
    write_json(FREEZE, {'code_commit': BASE, 'production_tag': 'v1.1.0',
        'runner_sha256': sha(Path(__file__)), 'tracked_blobs': blobs,
        'cases_file_sha256': sha(DATA), 'cases_digest': digest(cases),
        'manifest_sha256': sha(MANIFEST), 'reference_date': manifest['reference_date'],
        'database': manifest['database'], 'seed': manifest['seed'], 'config': config,
        'protocol_note': 'Existing dataset and manifest contain no per-case should_clarify labels or explicit universal must-proceed contract; report trigger rate, not unnecessary clarification rate.',
        'created_unix': time.time()})
    print('Frozen 300 cases, original database, code and identical mode configuration', flush=True)


def validate():
    f = read(FREEZE)
    assert f['runner_sha256'] == sha(Path(__file__)), 'Runner changed after freeze'
    assert git('rev-parse', 'v1.1.0^{commit}') == BASE
    assert f['config'] == public_config(), 'Run configuration changed'
    verify_files(f['tracked_blobs'])
    assert sha(DATA) == f['cases_file_sha256'] and sha(MANIFEST) == f['manifest_sha256']
    assert fingerprint(fetch_all) == f['database'], 'Database snapshot changed'
    return f


def candidate(question, reference, mode):
    # The only candidate inputs: original user question, fixed date and toggle.
    if mode == 'off':
        return scoped.direct(question, reference)
    if mode == 'on':
        return scoped.run_interactive(question, reference_date=reference)
    raise ValueError('Unknown mode')


def measured_call(question, reference, mode):
    start = time.perf_counter()
    with capture_usage() as usage:
        try:
            payload = candidate(question, reference, mode)
        except Exception as exc:
            payload = {'status': 'system_error', 'result': [], 'sql': '',
                       'error': type(exc).__name__}
    return {'state': 'complete', 'payload': clean(payload), 'usage': usage,
            'elapsed_s': round(time.perf_counter() - start, 6)}


def append(event):
    with RAW.open('a') as file:
        file.write(json.dumps(event, ensure_ascii=False) + '\n')
        file.flush()
        os.fsync(file.fileno())


def records():
    output = {}
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            event = json.loads(line)
            key = (event['id'], event['mode'])
            if key in output and output[key]['state'] == 'complete':
                raise RuntimeError('Duplicate completed call in immutable event log')
            output[key] = event
    return output


def run():
    f = validate()
    cases = read(DATA)
    reference = date.fromisoformat(f['reference_date'])
    previous = records()
    for (cid, mode), event in list(previous.items()):
        if event['state'] == 'started':
            end = {'id': cid, 'mode': mode, 'state': 'complete', 'elapsed_s': None,
                'usage': None, 'payload': {'status': 'system_error', 'result': [], 'sql': '',
                'error': 'Interrupted after scheduling; not rerun because API completion is unknown'}}
            append(end)
            previous[(cid, mode)] = end
    entity_context()  # Warm the same read-only city cache for both modes; no model call.
    done = sum(e['state'] == 'complete' for e in previous.values())
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for batch, offset in enumerate(range(0, len(cases), BATCH)):
            for mode in (('off', 'on') if batch % 2 == 0 else ('on', 'off')):
                todo = iter(c for c in cases[offset:offset+BATCH] if (c['id'], mode) not in previous)
                pending = {}
                exhausted = False
                while pending or not exhausted:
                    while len(pending) < WORKERS and not exhausted:
                        c = next(todo, None)
                        if c is None:
                            exhausted = True
                            break
                        append({'id': c['id'], 'mode': mode, 'state': 'started',
                                'started_unix': time.time()})
                        pending[pool.submit(measured_call, c['question'], reference, mode)] = c['id']
                    if not pending:
                        break
                    completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in completed:
                        cid = pending.pop(future)
                        event = {'id': cid, 'mode': mode, **future.result()}
                        append(event)
                        previous[(cid, mode)] = event
                        done += 1
                        if done % 10 == 0:
                            print(f'Persisted first-turn calls {done}/600; mode={mode}', flush=True)
    validate()
    assert len(previous) == 600
    print('Both fresh 300-case runs complete; no follow-up answers supplied', flush=True)


def ratio(n, d):
    return {'n': n, 'd': d, 'percent': round(n / d * 100, 2) if d else None}


def latency(values):
    xs = sorted(x for x in values if x is not None)
    return {'observed': len(xs), 'missing': len(values)-len(xs),
        'mean_s': round(statistics.mean(xs), 6) if xs else None,
        'p50_s': round(statistics.median(xs), 6) if xs else None,
        'p95_s': round(xs[math.ceil(.95*len(xs))-1], 6) if xs else None}


def score(case, record):
    p = record['payload']
    completed = p.get('status') == 'success'
    return {'status': p.get('status', 'system_error'), 'first_turn_completed': completed,
        'correct': completed and compare(case['ground_truth_result'], p.get('result', []), case['ordered']),
        'decision': p.get('gate_decision', {}).get('decision'),
        'triggered': p.get('status') == 'needs_clarification', 'sql': p.get('sql', ''),
        'result': p.get('result', []), 'error': p.get('error', ''),
        'elapsed_s': record['elapsed_s'], 'model_calls': len(record['usage']) if record['usage'] is not None else None}


def summarize():
    freeze = validate()
    cases, raw = read(DATA), records()
    assert len(raw) == 600 and all(r['state'] == 'complete' for r in raw.values())
    rows = []
    paired = Counter({'both_correct': 0, 'off_correct_on_wrong_or_incomplete': 0,
                      'off_wrong_on_correct': 0, 'both_wrong_or_incomplete': 0})
    for c in cases:
        off, on = (score(c, raw[(c['id'], mode)]) for mode in ('off', 'on'))
        pair = ('both_correct' if off['correct'] and on['correct'] else
                'off_correct_on_wrong_or_incomplete' if off['correct'] else
                'off_wrong_on_correct' if on['correct'] else 'both_wrong_or_incomplete')
        paired[pair] += 1
        rows.append({'id': c['id'], 'question': c['question'], 'category': c['category'],
            'difficulty': c['difficulty'], 'paraphrase': c['paraphrase'],
            'off': off, 'on': on, 'pair': pair, 'ground_truth_result': c['ground_truth_result']})
    metrics = {'total': 300, 'paired': dict(paired), 'code_commit': BASE,
               'reference_date': freeze['reference_date'], 'database_unchanged': True}
    for mode in ('off', 'on'):
        items = [r[mode] for r in rows]
        usage = [u for c in cases for u in (raw[(c['id'], mode)]['usage'] or [])]
        metrics[mode] = {'accuracy': ratio(sum(r['correct'] for r in items), 300),
            'latency': latency([r['elapsed_s'] for r in items]),
            'first_turn_completion': ratio(sum(r['first_turn_completed'] for r in items), 300),
            'status_counts': dict(Counter(r['status'] for r in items)),
            'model_calls_observed': len(usage), 'average_model_calls': round(len(usage)/300, 6),
            'model_call_count_missing_cases': sum(r['model_calls'] is None for r in items),
            'missing_token_usage_calls': sum(u['input_tokens'] is None or u['output_tokens'] is None for u in usage),
            'category_accuracy': {cat: ratio(sum(r[mode]['correct'] for r in rows if r['category']==cat),
                sum(r['category']==cat for r in rows)) for cat in sorted({r['category'] for r in rows})}}
    on = metrics['on']
    proceed = [r for r in rows if r['on']['decision'] == 'proceed']
    trigger = [r['id'] for r in rows if r['on']['triggered']]
    on.update(proceed_count=len(proceed), clarify_count=len(trigger), trigger_rate=ratio(len(trigger), 300),
        proceed_subset_accuracy=ratio(sum(r['on']['correct'] for r in proceed), len(proceed)),
        decision_counts=dict(Counter(r['on']['decision'] or r['on']['status'] for r in rows)),
        clarification_case_ids=trigger)
    regressions = [r for r in rows if r['pair']=='off_correct_on_wrong_or_incomplete']
    metrics['regression_on_status_counts'] = dict(Counter(r['on']['status'] for r in regressions))
    metrics['regression_case_ids'] = [r['id'] for r in regressions]
    metrics['delta_pp'] = round((metrics['on']['accuracy']['n']-metrics['off']['accuracy']['n'])/300*100, 2)
    for suffix, value in [('per_case', rows), ('report', metrics),
            ('bad_cases', [r for r in rows if not r['off']['correct'] or not r['on']['correct']])]:
        write_json(Path(str(PREFIX) + '_' + suffix + '.json'), value)
    write_report(metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def write_report(m):
    a, b = m['off'], m['on']
    lines = ['# Fixed 300-case Clarification Regression', '',
        '## 首轮配对结果', '', '```text', 'Fixed 300-case Regression Benchmark', '',
        'Clarification OFF', f"Accuracy = {a['accuracy']['percent']:.2f}% ({a['accuracy']['n']}/300)",
        f"Avg latency = {a['latency']['mean_s']:.2f}s", '', 'Clarification ON',
        f"First-turn Result Accuracy = {b['accuracy']['percent']:.2f}% ({b['accuracy']['n']}/300)",
        f"Avg latency = {b['latency']['mean_s']:.2f}s",
        f"Clarification Trigger Rate = {b['clarify_count']}/300 ({b['trigger_rate']['percent']:.2f}%)", '',
        f"Delta = {m['delta_pp']:+.2f} pp", '```', '',
        '| 指标 | OFF | ON |', '|---|---:|---:|']
    for label, av, bv in [
        ('P50 latency (s)', a['latency']['p50_s'], b['latency']['p50_s']),
        ('P95 latency (s)', a['latency']['p95_s'], b['latency']['p95_s']),
        ('Average model calls', a['average_model_calls'], b['average_model_calls']),
        ('Model calls observed', a['model_calls_observed'], b['model_calls_observed']),
        ('Missing call-count cases', a['model_call_count_missing_cases'], b['model_call_count_missing_cases']),
        ('Missing token-usage calls', a['missing_token_usage_calls'], b['missing_token_usage_calls']),
        ('首轮完成率', str(a['first_turn_completion']), str(b['first_turn_completion']))]:
        lines.append(f'| {label} | {av} | {bv} |')
    lines += ['', '首轮完成定义：无需用户补充且 SQL 执行成功；不等同于结果正确。',
        '准确率始终基于 SQL 结果与原 Ground Truth 的严格比较，分母均为300。',
        '耗时为工作线程中生产调用的墙钟时间，含Gate和原有重试，不含排队、结果落盘或用户思考。',
        'P50为中位数，P95为nearest-rank。模型调用由原capture_usage统计；SDK内部网络重试不是单独模型调用。', '',
        '## Gate与逐题配对', '',
        f"Proceed = {b['proceed_count']}；Clarify = {b['clarify_count']}。",
        f"Proceed子集结果准确率：{b['proceed_subset_accuracy']}。",
        f"其他状态与计数：`{json.dumps(b['decision_counts'], ensure_ascii=False)}`。", '',
        '| 配对 | 题数 |', '|---|---:|']
    for name, key in [('OFF正确 → ON正确', 'both_correct'),
        ('OFF正确 → ON错误/未完成', 'off_correct_on_wrong_or_incomplete'),
        ('OFF错误 → ON正确', 'off_wrong_on_correct'),
        ('OFF错误 → ON错误/未完成', 'both_wrong_or_incomplete')]:
        lines.append(f"| {name} | {m['paired'][key]} |")
    lines += ['', f"配对回退中ON状态分布：`{json.dumps(m['regression_on_status_counts'], ensure_ascii=False)}`。",
        '这是本次开启设置后的观测回退；两次独立SQL采样仍有随机性，不能把全部差异都归因为反问。', '',
        '### 触发澄清的case id', '', ', '.join(b['clarification_case_ids']) or '无', '',
        '### OFF正确而ON错误/未完成的case id', '', ', '.join(m['regression_case_ids']) or '无', '',
        '## 协议与证据', '',
        f'生产代码固定为 `{BASE}`（`v1.1.0`），没有修改生产逻辑、Prompt、Gate、城市元数据或评分代码。',
        '使用原 `eval/final_release_holdout_300.json` 和 `eval/final_release_manifest.json`；',
        '参考日期2026-09-12，原seed与七张表指纹不变；没有重新seed、改城市、修改Ground Truth或删除失败题。',
        '两边使用qwen-plus，同一个SQL temperature；Gate保持原temperature=0。具体参数与SDK超时默认值见freeze。',
        '每种模式最多4并发，按20题批次交替先后顺序；共享只读城市缓存预热，不调用embedding。',
        '每题每种模式首次运行一次，保留生产重试但不增加评测重试；已保存调用不重复执行。',
        '候选入口只接受原问题、参考日期、开关；没有传入标准SQL、Ground Truth或评测标签。',
        'ON触发反问后立即结束，没有任何模拟用户回答；needs_rephrase、invalid_output和system_error等同样保留在总分母。',
        '原题库与manifest没有should_clarify标签，也未提供可核验的全体必须proceed协议，因此只报告Trigger Rate，不把所有反问定性为不必要澄清。',
        '配对逐题结果及全部失败案例分别见 `eval/clarification_300_regression_per_case.json` 与 `_bad_cases.json`。',
        '完整首次调用、usage、反问及错误见 `eval/clarification_300_regression_events.jsonl`；冻结配置与文件哈希见 `_freeze.json`。',
        '若发生启动后中断且模型完成状态不可确认，保留为未完成、不重跑，并单独报告缺失耗时/调用统计。', '',
        '## 与120题评测的边界', '',
        '本报告是已揭晓的300题回归测试，只测开启Gate对首轮原查询能力的影响，不是新盲测。',
        '120题专项评测衡量允许一轮用户补充的交互收益：59.17% → 73.33%，+14.17pp，Clarification F1 93.10%。',
        '两者题库、可用信息和目的不同，不拼接准确率、延迟或提升百分点；F1不是端到端准确率。',
        '没有根据本次成绩调整系统或题目。', '',
        '## 测试', '', '本次pytest与runner离线自检结果见 `eval/clarification_300_regression_pytest.json`。', '']
    REPORT.write_text('\n'.join(lines))


def self_test():
    ref = date(2026, 9, 12)
    with patch.object(scoped, 'direct', return_value={'status': 'success'}) as direct, \
         patch.object(scoped, 'run_interactive', return_value={'status': 'needs_clarification'}) as interactive:
        candidate('q', ref, 'off')
        direct.assert_called_once_with('q', ref)
        interactive.assert_not_called()
        candidate('q', ref, 'on')
        interactive.assert_called_once_with('q', reference_date=ref)
    case = {'ground_truth_result': [{'n': 1}], 'ordered': False}
    record = {'payload': {'status': 'needs_clarification', 'result': [{'n': 1}]}, 'usage': [], 'elapsed_s': 1}
    assert not score(case, record)['correct'] and not score(case, record)['first_turn_completed']
    record['payload'] = {'status': 'success', 'result': [{'n': 2}]}
    assert not score(case, record)['correct'] and score(case, record)['first_turn_completed']
    assert ratio(150, 300)['percent'] == 50
    assert latency([1, 2, 3, 4])['p95_s'] == 4
    print('Runner offline self-test passed: toggle isolation, no follow-up inputs, denominator, completion vs correctness, percentile')


def tests():
    self_test()
    result = subprocess.run([str(ROOT/'.venv/bin/python'), '-m', 'pytest', '-q'],
        cwd=ROOT, capture_output=True, text=True)
    value = {'returncode': result.returncode, 'stdout': clean(result.stdout),
             'stderr': clean(result.stderr), 'runner_self_test': 'passed'}
    write_json(Path(str(PREFIX)+'_pytest.json'), value)
    print(value['stdout'])
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'run', 'summarize', 'self-test', 'test'])
    args = parser.parse_args()
    with (ROOT/'.run/clarification_300_regression.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        {'prepare': prepare, 'run': run, 'summarize': summarize, 'self-test': self_test, 'test': tests}[args.phase]()
