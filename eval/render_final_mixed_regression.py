"""Render current regression evidence without changing the frozen comparator."""

from collections import Counter
import json
from pathlib import Path

from eval.scoring import write_json

ROOT = Path(__file__).resolve().parents[1]


def read(suffix):
    return json.loads((ROOT / ('eval/final_mixed_regression_' + suffix)).read_text())


def ratio(n, d):
    return {'n': n, 'd': d, 'percent': round(100 * n / d, 2) if d else None}


def fmt(value):
    percent = value['percent']
    return f"{percent:.2f}% ({value['n']}/{value['d']})" if percent is not None else f"N/A ({value['n']}/{value['d']})"


def render():
    metrics, rows, freeze = read('report.json'), read('per_case.json'), read('freeze.json')
    events = {}
    for line in (ROOT / 'eval/final_mixed_regression_events.jsonl').read_text().splitlines():
        event = json.loads(line)
        if event['state'] == 'complete':
            key = (event['id'], event['stage'])
            assert key not in events
            events[key] = event
    assert len(rows) == 200 and len({r['id'] for r in rows}) == 200
    assert all((r['id'], m) in events for r in rows for m in ('off', 'on'))
    supplemental = {
        'trigger_rate': ratio(sum(r['triggered'] for r in rows), 200),
        'overall_strict_success': ratio(sum(
            (r['kind'] == 'clear' and r['decision'] == 'proceed' and r['on_correct'])
            or r['strict_ambiguous_success'] for r in rows), 200),
        'status_counts': {m: dict(Counter(r[m + '_status'] for r in rows)) for m in ('off', 'on')},
        'usage': {},
        'model_calls_total': {m: sum(r[m + '_calls'] for r in rows) for m in ('off', 'on')},
        'completed_stages': len(events),
    }
    for mode in ('off', 'on'):
        usage = [u for (_, stage), event in events.items()
                 if stage == mode or (mode == 'on' and stage == 'followup') for u in event['usage']]
        supplemental['usage'][mode] = {
            'calls': len(usage),
            'complete_token_records': sum(u.get('input_tokens') is not None and u.get('output_tokens') is not None for u in usage),
            'observed_input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
            'observed_output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
        }
    write_json(ROOT / 'eval/final_mixed_regression_supplement.json', supplemental)
    lines = [
        '# QueryMate Final Mixed Clarification Regression', '',
        'This is a regression evaluation on an already disclosed frozen benchmark, not a new blind benchmark.', '',
        '## Protocol and Freeze', '',
        f"- Functional freeze commit: `{freeze['code_commit']}`.",
        '- Browser manual verification: **PASS — manually verified by user**. No automated browser pass claimed.',
        '- Fixed dataset: 200 synthetic cases; clear 140, single ambiguity 60 (time 20, metric 20, entity/filter 20). This distribution does not represent production traffic.',
        f"- Dataset SHA256: `{freeze['hashes']['eval/final_mixed_cases.json']}`.",
        f"- Comparator SHA256: `{freeze['hashes']['eval/scoring.py']}`.",
        f"- Reference date: `{freeze['reference_date']}`; seed: `{freeze['database_seed']}`. Database fingerprints are recorded in `eval/final_mixed_regression_freeze.json`.",
        '- Both modes use the same code, qwen-plus, business/schema/city context, MySQL snapshot, SQL engine, guardrail, retry and scorer. SQL temperature 0.05; Gate temperature 0. Embedding configuration remains text-embedding-v4; this production route makes no embedding calls.',
        '- OFF bypasses Gate. ON uses JSON Object plus Pydantic; one reviewed, pre-frozen slot answer is supplied only after an actual clarification. No reference SQL, Ground Truth or resolved full question is passed to the candidate.',
        '- OFF and ON each run serially. First-turn order alternates by case; audited follow-ups run after first turns. Latencies sum measured system processing across turns, excluding review/user thinking time.',
        '- ON receives extra user information when clarification is answerable. This compares interactive task outcomes, not equal-information model ability.',
        '- No case, Ground Truth, difficulty, prompt, validator, engine or scoring changes were made after functional freeze. No failure cases were removed.', '',
        '## Result Accuracy', '',
        '| Subset | OFF | ON | Delta pp |', '|---|---:|---:|---:|',
    ]
    for label in ('overall', 'clear', 'ambiguous'):
        off, on = metrics['off'][label], metrics['on'][label]
        delta = 100 * (on['n'] / on['d'] - off['n'] / off['d'])
        lines.append(f"| {label} | {fmt(off)} | {fmt(on)} | {delta:+.2f} |")
    lines += ['', '## Clarification and Strict Interaction', '',
              '| Metric | ON |', '|---|---:|']
    for label, value in [
        ('Decision accuracy', metrics['clarification_accuracy']),
        ('Precision', metrics['precision']), ('Recall', metrics['recall']), ('F1', metrics['f1']),
        ('Trigger rate', supplemental['trigger_rate']),
        ('Unnecessary clarification / clear cases', metrics['unnecessary']),
        ('Missed clarification / ambiguous cases', metrics['missed']),
        ('Ambiguous strict interactive success', metrics['strict_ambiguous_success']),
        ('Overall strict interactive success', supplemental['overall_strict_success']),
    ]:
        lines.append(f'| {label} | {fmt(value)} |')
    lines += ['', 'F1 reports its formula counts: 2TP / (2TP + FP + FN), not a case count. '
              'Ambiguous strict success uses the original scorer: an actual clarification, an eligible frozen answer, preserved context and slot evidence, then a matching result. '
              'Overall strict success adds clear cases that proceeded and matched. Format/system failures remain in the denominators.', '',
              '## Efficiency', '', '| Metric | OFF | ON |', '|---|---:|---:|']
    for key in ('mean_s', 'p50_s', 'p95_s'):
        lines.append(f"| {key} | {metrics['off']['latency'][key]:.3f}s | {metrics['on']['latency'][key]:.3f}s |")
    lines.append(f"| Average model calls | {metrics['off']['average_model_calls']:.3f} ({supplemental['model_calls_total']['off']}/200) | {metrics['on']['average_model_calls']:.3f} ({supplemental['model_calls_total']['on']}/200) |")
    for mode in ('off', 'on'):
        u = supplemental['usage'][mode]
        lines.append(f"\n{mode.upper()} token records: {u['complete_token_records']}/{u['calls']} complete; observed input {u['observed_input_tokens']}, output {u['observed_output_tokens']}. Missing usage is not estimated.")
    lines += ['', '## Paired Results', '', '| OFF -> ON | Cases |', '|---|---:|']
    for pair in ('off_correct_on_correct', 'off_correct_on_wrong', 'off_wrong_on_correct', 'off_wrong_on_wrong'):
        lines.append(f"| {pair} | {metrics['paired'].get(pair, 0)}/200 |")
    lines += ['', '## Failures and Limitations', '',
              f"- Infrastructure failures: {metrics['infrastructure_failures']}; completed stages: {len(events)}.",
              f"- Final status counts: `{json.dumps(supplemental['status_counts'], ensure_ascii=False)}`.",
              '- Full failures are preserved in `eval/final_mixed_regression_bad_cases.json`; all 200 paired cases are in `eval/final_mixed_regression_per_case.json`.',
              '- A result match does not prove semantic equivalence on other data. The frozen comparator retains its original numeric tolerance and empty-result behavior.',
              '- One-turn clarification cannot resolve every business ambiguity. Correct Gate decisions do not guarantee correct multi-table aggregation or SQL semantics.',
              '- This disclosed, self-authored synthetic set cannot establish generalization to unseen business traffic. No statistical significance claim is made.',
              '- Historical 69.0% -> 73.5% remains in `FINAL_MIXED_CLARIFICATION_EVALUATION.md` and is not attributed to this code.', '',
              'Examples below are diagnostic pointers, not exclusions:', '',
              '| Case | Kind | OFF | ON | Triggered | Strict ambiguous success |', '|---|---|---|---|---|---|']
    failures = [r for r in rows if not r['off_correct'] or not r['on_correct'] or (r['kind'] != 'clear' and not r['strict_ambiguous_success'])]
    for row in failures[:15]:
        lines.append(f"| {row['id']} | {row['kind']} | {row['off_correct']} | {row['on_correct']} | {row['triggered']} | {row['strict_ambiguous_success']} |")
    lines += ['', '## Reproducibility', '',
              '- Frozen protocol: `eval/final_mixed_regression_freeze.json`; execution identity: `eval/final_mixed_regression_run_freeze.json`.',
              '- Runner: `eval/run_final_mixed_regression.py`; it reuses the original candidate calls and `run_final_mixed.summarize`, redirecting only output paths.',
              '- Actual clarification/answer eligibility: `final_mixed_regression_reply_packet.json`, `reply_review.json`, `reply_freeze.json` under `eval/` with the same regression prefix.',
              '- All attempts: `eval/final_mixed_regression_events.jsonl`. Started-but-unobserved requests are never automatically repeated.',
              '- `python -m eval.run_final_mixed_regression summarize` and `python -m eval.render_final_mixed_regression` regenerate reports from saved results without paid model calls.',
              '- Original 120/200/300 reports, timeout diagnosis, repair report, valid authoring provenance, LICENSE and attribution remain preserved.', '',
              '## Release Acceptance', '',
              'Post-evaluation pytest: **133 passed, 2 warnings**. Project stop/start, Streamlit homepage and FastAPI docs/health checks passed. '
              'Browser: **PASS — manually verified by user**, not automated browser testing. '
              'See [release acceptance](docs/QUERYMATE_V1_2_RELEASE_ACCEPTANCE.md) for scope, cleanup provenance and release conditions.', '']
    (ROOT / 'FINAL_MIXED_CLARIFICATION_REGRESSION.md').write_text('\n'.join(lines))
    print(json.dumps({'delta_pp': metrics['delta_pp'], **supplemental}, ensure_ascii=False))


if __name__ == '__main__':
    render()
