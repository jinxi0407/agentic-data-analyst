"""Render evidence already measured by the frozen runner; no model or database calls."""

import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


def ratio(x):
    return f"{x['percent']:.2f}% ({x['n']}/{x['d']})" if x['percent'] is not None else f"N/A ({x['n']}/{x['d']})"


def render():
    r=read('eval/final_mixed_report.json')
    cases=read('eval/final_mixed_per_case.json')
    freeze=read('eval/final_mixed_freeze.json')
    run=read('eval/final_mixed_run_freeze.json')
    audit=read('eval/final_mixed_authoring_revision_1/semantic_review.json')
    tests=read('eval/final_mixed_test_evidence.json')
    off,on=r['off'],r['on']
    clear=[x for x in cases if x['kind']=='clear']
    regressions=[x for x in clear if x['off_correct'] and not x['on_correct']]
    recoveries=[x for x in clear if not x['off_correct'] and x['on_correct']]
    ambiguous_delta=on['ambiguous']['percent']-off['ambiguous']['percent']
    pairs=r['paired']
    lines=[
      '# Final Mixed Clarification Evaluation',
      '',
      'Status: completed once on the locally frozen dataset. No post-result Gate, Prompt, validator, schema, business-rule or question changes.',
      '',
      '## Scope And Interpretation',
      '',
      'This is a **self-built synthetic mixed evaluation**, not a representative sample of live requests. '
      'The fixed composition is **200 = 140 clear + 60 single-ambiguity**: 20 time, 20 metric and 20 entity/filter cases. '
      'ON can receive one extra, pre-frozen user answer after asking a matching clarification question. '
      'This measures **interactive task completion**, not model ability under equal information.',
      '',
      'The old 300 cases are revealed regression/development evidence. The historical 120-case clarification study '
      'has a different purpose and dataset; its 59.17% -> 73.33% (+14.17pp) and F1 93.10% are not reused or combined with the new results.',
      '',
      '## Resumed 300-Case Regression',
      '',
      '| Metric | Historical ON | Optimized ON |',
      '|---|---:|---:|',
      '| Clarification trigger | 122/300 (40.67%) | 0/300 (0.00%) |',
      '| First-turn result accuracy | 99/300 (33.00%) | 228/300 (76.00%) |',
      '| OFF correct -> ON incomplete | 130 | 0 |',
      '',
      'Reused OFF: **232/300 (77.33%)**. Fresh ON delta: **-1.33pp**. '
      'The saved OFF was independently re-scored and its engine/direct-path inputs, public model parameters, '
      'business/schema context, original dataset and database fingerprint were verified unchanged. No OFF calls were repeated.',
      '',
      'Paired counts: OFF correct -> ON correct 228; OFF correct -> ON wrong 4; '
      'OFF correct -> ON incomplete 0; OFF wrong -> ON correct 0; OFF wrong -> ON wrong/incomplete 68. '
      'The incomplete count fell by **130**. There were 296 successful SQL workflows, four failed workflows, '
      'and **zero observed transport/API failures**. All 300 Gate decisions were proceed; no simulated answers were supplied.',
      '',
      '| 300-case timing | OFF saved | ON fresh serial |',
      '|---|---:|---:|',
      '| Mean seconds | 2.759772 | 4.028097 |',
      '| P50 seconds | 2.196696 | 3.407051 |',
      '| P95 seconds | 6.876529 | 8.288846 |',
      '| Average model calls | 1.08 | 2.08 |',
      '',
      'OFF originally used four workers; the resumed ON used one. These latency figures are descriptive, '
      'not a controlled estimate of Gate overhead. Provider aliases/request dates also limit reproducibility. '
      'Zero triggers on revealed data do not establish recall on ambiguous requests. The earlier offline 122-trigger '
      'audit classified A genuinely unresolved = 2, B resolvable by contract/schema/time = 116, C defective output = 4; '
      'these remain diagnostic reviewer judgments, not new benchmark labels.',
      '',
      '## Freeze And Data Provenance',
      '',
      f"- Gate freeze commit: `{freeze['gate_freeze_commit']}`; implementation `8fb1e3a`.",
      f"- Dataset/evaluation commit before any candidate calls: `{run['data_commit']}`.",
      f"- Manifest SHA-256: `{run['manifest_sha256']}`.",
      f"- Reference date: `{freeze['reference_date']}`; database seed `{freeze['database_seed']}`. The original 300-case generation seed `{freeze['original_300_benchmark_seed']}` is not the database seed.",
      '- Database table fingerprints, protected production hashes, dataset, runner, scorer and protocol hashes: `eval/final_mixed_freeze.json`.',
      '- Models: qwen-plus and text-embedding-v4 unchanged; this production workflow performs no embedding requests. SQL temperature 0.05, Gate temperature 0, execution retry limit 2, existing Gate format retry limit 1.',
      '- Both fresh modes use concurrency 1, alternate first-turn order by case, and share the same production engine/context/metadata/guardrail/retry/scorer. First turns precede a separately audited follow-up phase.',
      '- Gate timeout remains 5s connect / 30s read; production SQL transport defaults are unchanged. No evaluation-level retries or repeat of completed calls. An infrastructure failure stops scheduling.',
      '',
      'Independent authoring model inputs were restricted to the protocol, synthetic database schema/metadata and business contract. '
      'They did not contain the Gate prompt or historical failure outputs. Raw responses, rejected drafts and every pre-freeze correction '
      'are retained under `eval/final_mixed_authoring*`. The initial draft batch was stopped for repetition; those drafts were never candidate-tested. '
      'Local review corrected unsupported fields, duplicated aggregation, missing/incorrect ambiguity labels, ties, and reference SQL syntax '
      'before freeze. This is internal authoring/review, not an external independent benchmark.',
      '',
      f"Historical question/reference-only screening covered {audit['historical_questions_screened']} records; it never used their failed model outputs. "
      'Alias/literal-normalized and order/limit/round-insensitive structural screening found no unresolved exact-template matches at freeze. '
      'This does not prove semantic novelty: core business operators necessarily recur. References were executed read-only on the unchanged MySQL snapshot. '
      f"All {freeze['empty_reference_results']} legitimate empty reference results were retained. No question was changed after candidate execution began.",
      '',
      '## Mixed Results',
      '',
      '| Result accuracy | OFF Baseline | ON Final |',
      '|---|---:|---:|',
      f"| All 200 | {ratio(off['overall'])} | {ratio(on['overall'])} |",
      f"| Clear 140 | {ratio(off['clear'])} | {ratio(on['clear'])} |",
      f"| Ambiguous 60 | {ratio(off['ambiguous'])} | {ratio(on['ambiguous'])} |",
      '',
      f"**Overall delta: {r['delta_pp']:+.2f}pp.** Ambiguous-query delta: {ambiguous_delta:+.2f}pp.",
      f"Clear subset: {len(regressions)} OFF-correct cases became ON-wrong/incomplete; {len(recoveries)} OFF-wrong cases became ON-correct.",
      '',
      '| Clarification measure | Value |',
      '|---|---:|',
      f"| Decision accuracy | {ratio(r['clarification_accuracy'])} |",
      f"| Precision | {ratio(r['precision'])} |",
      f"| Recall | {ratio(r['recall'])} |",
      f"| F1 | {ratio(r['f1'])} |",
      f"| Unnecessary clarification / clear | {ratio(r['unnecessary'])} |",
      f"| Missed clarification / ambiguous | {ratio(r['missed'])} |",
      f"| Strict ambiguous interactive success | {ratio(r['strict_ambiguous_success'])} |",
      '',
      'Strict interactive success requires a triggered, answerable clarification, the exact frozen single-slot answer actually supplied, '
      'preservation of the original question/known constraints, quoted resolved information from that answer in the engine input, and a correct final SQL result. '
      'Its denominator is all 60 ambiguous cases, not just successfully clarified cases. Raw result accuracy may include coincidental correct answers '
      'without clarification; it is intentionally reported separately.',
      '',
      '| Paired outcome | Count |',
      '|---|---:|',
      f"| OFF correct -> ON correct | {pairs.get('off_correct_on_correct',0)} |",
      f"| OFF correct -> ON wrong/incomplete | {pairs.get('off_correct_on_wrong',0)} |",
      f"| OFF wrong -> ON correct | {pairs.get('off_wrong_on_correct',0)} |",
      f"| OFF wrong -> ON wrong/incomplete | {pairs.get('off_wrong_on_wrong',0)} |",
      '',
      '| System processing cost | OFF | ON |',
      '|---|---:|---:|',
    ]
    for key,title in [('mean_s','Mean seconds'),('p50_s','P50 seconds'),('p95_s','P95 seconds')]:
        lines.append(f"| {title} | {off['latency'][key]:.6f} | {on['latency'][key]:.6f} |")
    lines += [f"| Average model calls | {off['average_model_calls']:.3f} | {on['average_model_calls']:.3f} |",'',
      'Latency sums actual system processing across performed turns, excluding local answer review/simulated thinking and queue wait. '
      'Model calls count wrapper calls, including format/execution retries; hidden SDK wire retries are not separately observable.',
      f"Observed infrastructure failures: **{r['infrastructure_failures']}**. Decision counts: `{json.dumps(r['decision_counts'],ensure_ascii=False)}`.",'',
      '## Answer Isolation And Failure Evidence','',
      'Candidate functions accept only the public question/reference date and mode. Neither Reference SQL, Ground Truth, intended full meaning nor '
      'should_clarify labels enter candidate requests. Follow-up review packets contain only the original question, actual Gate question and frozen '
      'single-slot answer. No answer is supplied for clear cases or an unrelated clarification. Slot-enum equality alone is not sufficient: '
      'a local reviewer must confirm the literal answer addresses the actual question. Reviews are frozen before follow-up requests.',
      '',
      '- Complete immutable calls and outputs: `eval/final_mixed_events.jsonl`.',
      '- Per-case results: `eval/final_mixed_per_case.json`; all failed/strict-failed cases: `eval/final_mixed_bad_cases.json`.',
      '- Actual clarification eligibility decisions: `eval/final_mixed_reply_review.json`; review hashes: `eval/final_mixed_reply_freeze.json`.',
      '',
      '### Failure Breakdown',
      '',
      '| Ambiguity type | OFF correct / 20 | ON correct / 20 | Triggered / 20 | Strict success / 20 |',
      '|---|---:|---:|---:|---:|',
    ]
    for kind in ('time','metric','entity_filter'):
        subset=[x for x in cases if x['kind']==kind]
        lines.append(f"| {kind} | {sum(x['off_correct'] for x in subset)} | {sum(x['on_correct'] for x in subset)} | {sum(x['triggered'] for x in subset)} | {sum(x['strict_ambiguous_success'] for x in subset)} |")
    lines += ['',
      'The conservative Gate still missed **31/60** ambiguous cases, including four first-turn `invalid_output` records. '
      'Among the 29 follow-ups, 17 reached SQL success, four failed SQL workflows, and eight returned `invalid_output` '
      '(structured decision/validation failure, not a transport timeout). Only **12/29 (41.38%)** triggered cases '
      'achieved a correct final result, equivalent to **12/60 (20.00%)** strict interactive success across all ambiguity cases. '
      'Metric ambiguity results regressed from 10/20 to 8/20; that regression is retained, not hidden by the overall gain.',
      '',
      'One actual question (`final_mixed_191`) gave refund-reason examples not present in stored metadata. '
      'The open-ended question could still be answered by the frozen valid reason. This remains an observed UX limitation, not a reason to edit the Gate.',
      '',
      'Representative failures below are descriptive only; no resulting changes were made:',
    ]
    examples=[]
    for group in ([x for x in cases if x['kind']=='clear' and not x['on_correct']],
                  [x for x in cases if x['kind']!='clear' and not x['triggered'] and not x['on_correct']],
                  [x for x in cases if x['triggered'] and not x['on_correct']]):
        examples.extend(group[:3])
    for x in examples:
        lines.append(f"- `{x['id']}` ({x['kind']}): OFF correct={x['off_correct']}, ON correct={x['on_correct']}, ON status={x['on_status']}. {x['question']}")
    lines += ['', '## Limitations And Final Checks','',
      '- Self-built synthetic questions and internal semantic review can introduce selection/label bias; results do not establish online-user performance.',
      '- The shared frozen scorer matches SQL results, not mere successful execution. It ignores column aliases/permutation, respects ordered rows when specified, and uses absolute numeric tolerance 0.005. Small ratio differences or empty results can coincide even with different SQL semantics; the scorer was not changed.',
      '- One frozen answer turn cannot resolve an unrelated question or multiple missing choices. Unanswerable follow-ups remain failures with the original denominator.',
      '- Qwen floating model aliases, nonzero SQL temperature and network timing limit deterministic reproducibility. No reruns were used to pick a favorable result.',
      f"- Final pytest: **{tests['passed']} passed, {tests['warnings']} warnings**, {tests['elapsed_s']:.2f}s. Existing AnyIO and DashScope deprecations; evidence in `eval/final_mixed_test_evidence.json`.",
      '- Production/Gate/Prompt/validator/schema/business/SQL engine hashes remained frozen; database data, historical benchmarks and scores were not edited.',
      '- Preserved: `docs/GATE_TIMEOUT_DIAGNOSIS.md`, `FINAL_300_CLARIFICATION_REGRESSION.md`, `FINAL_CLARIFICATION_EVALUATION.md` and prior evaluation artifacts.',
      '- Local evidence only. No main merge, push, new tag, resume-number update, additional optimization or Financial/EduRAG Docker action.',
    ]
    (ROOT/'FINAL_MIXED_CLARIFICATION_EVALUATION.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    render()
