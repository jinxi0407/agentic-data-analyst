# QueryMate Final Mixed Clarification Regression

This is a regression evaluation on an already disclosed frozen benchmark, not a new blind benchmark.

## Protocol and Freeze

- Functional freeze commit: `269a44121c56d0579f6c76303a0a43d96f746ca1`.
- Browser manual verification: **PASS — manually verified by user**. No automated browser pass claimed.
- Fixed dataset: 200 synthetic cases; clear 140, single ambiguity 60 (time 20, metric 20, entity/filter 20). This distribution does not represent production traffic.
- Dataset SHA256: `e97dc9038520993a080f0a9329c2730a9fdf47992bb98174a909535c8cd93167`.
- Comparator SHA256: `06f7e99378098fbecd650952dda4a82ea65481f8e197245a0d0e8546952ccac7`.
- Reference date: `2026-09-12`; seed: `20260911`. Database fingerprints are recorded in `eval/final_mixed_regression_freeze.json`.
- Both modes use the same code, qwen-plus, business/schema/city context, MySQL snapshot, SQL engine, guardrail, retry and scorer. SQL temperature 0.05; Gate temperature 0. Embedding configuration remains text-embedding-v4; this production route makes no embedding calls.
- OFF bypasses Gate. ON uses JSON Object plus Pydantic; one reviewed, pre-frozen slot answer is supplied only after an actual clarification. No reference SQL, Ground Truth or resolved full question is passed to the candidate.
- OFF and ON each run serially. First-turn order alternates by case; audited follow-ups run after first turns. Latencies sum measured system processing across turns, excluding review/user thinking time.
- ON receives extra user information when clarification is answerable. This compares interactive task outcomes, not equal-information model ability.
- No case, Ground Truth, difficulty, prompt, validator, engine or scoring changes were made after functional freeze. No failure cases were removed.

## Result Accuracy

| Subset | OFF | ON | Delta pp |
|---|---:|---:|---:|
| overall | 71.00% (142/200) | 77.50% (155/200) | +6.50 |
| clear | 89.29% (125/140) | 87.86% (123/140) | -1.43 |
| ambiguous | 28.33% (17/60) | 53.33% (32/60) | +25.00 |

## Clarification and Strict Interaction

| Metric | ON |
|---|---:|
| Decision accuracy | 86.00% (172/200) |
| Precision | 100.00% (32/32) |
| Recall | 53.33% (32/60) |
| F1 | 69.57% (64/92) |
| Trigger rate | 16.00% (32/200) |
| Unnecessary clarification / clear cases | 0.00% (0/140) |
| Missed clarification / ambiguous cases | 46.67% (28/60) |
| Ambiguous strict interactive success | 36.67% (22/60) |
| Overall strict interactive success | 72.50% (145/200) |

F1 reports its formula counts: 2TP / (2TP + FP + FN), not a case count. Ambiguous strict success uses the original scorer: an actual clarification, an eligible frozen answer, preserved context and slot evidence, then a matching result. Overall strict success adds clear cases that proceeded and matched. Format/system failures remain in the denominators.

## Efficiency

| Metric | OFF | ON |
|---|---:|---:|
| mean_s | 4.153s | 5.660s |
| p50_s | 2.796s | 4.769s |
| p95_s | 8.321s | 9.747s |
| Average model calls | 1.075 (215/200) | 2.225 (445/200) |

OFF token records: 215/215 complete; observed input 497908, output 22662. Missing usage is not estimated.

ON token records: 445/445 complete; observed input 1045044, output 33500. Missing usage is not estimated.

## Paired Results

| OFF -> ON | Cases |
|---|---:|
| off_correct_on_correct | 138/200 |
| off_correct_on_wrong | 4/200 |
| off_wrong_on_correct | 17/200 |
| off_wrong_on_wrong | 41/200 |

## Failures and Limitations

- Infrastructure failures: 0; completed stages: 432.
- Final status counts: `{"off": {"success": 195, "failed": 5}, "on": {"success": 194, "failed": 4, "invalid_output": 2}}`.
- Full failures are preserved in `eval/final_mixed_regression_bad_cases.json`; all 200 paired cases are in `eval/final_mixed_regression_per_case.json`.
- A result match does not prove semantic equivalence on other data. The frozen comparator retains its original numeric tolerance and empty-result behavior.
- One-turn clarification cannot resolve every business ambiguity. Correct Gate decisions do not guarantee correct multi-table aggregation or SQL semantics.
- This disclosed, self-authored synthetic set cannot establish generalization to unseen business traffic. No statistical significance claim is made.
- Historical 69.0% -> 73.5% remains in `FINAL_MIXED_CLARIFICATION_EVALUATION.md` and is not attributed to this code.

Examples below are diagnostic pointers, not exclusions:

| Case | Kind | OFF | ON | Triggered | Strict ambiguous success |
|---|---|---|---|---|---|
| final_mixed_029 | clear | True | False | False | False |
| final_mixed_032 | clear | False | False | False | False |
| final_mixed_035 | clear | False | False | False | False |
| final_mixed_036 | clear | False | False | False | False |
| final_mixed_039 | clear | False | False | False | False |
| final_mixed_049 | clear | False | False | False | False |
| final_mixed_050 | clear | False | False | False | False |
| final_mixed_068 | clear | False | False | False | False |
| final_mixed_082 | clear | False | False | False | False |
| final_mixed_086 | clear | True | False | False | False |
| final_mixed_089 | clear | False | False | False | False |
| final_mixed_102 | clear | False | False | False | False |
| final_mixed_103 | clear | False | False | False | False |
| final_mixed_106 | clear | False | False | False | False |
| final_mixed_109 | clear | False | False | False | False |

## Reproducibility

- Frozen protocol: `eval/final_mixed_regression_freeze.json`; execution identity: `eval/final_mixed_regression_run_freeze.json`.
- Runner: `eval/run_final_mixed_regression.py`; it reuses the original candidate calls and `run_final_mixed.summarize`, redirecting only output paths.
- Actual clarification/answer eligibility: `final_mixed_regression_reply_packet.json`, `reply_review.json`, `reply_freeze.json` under `eval/` with the same regression prefix.
- All attempts: `eval/final_mixed_regression_events.jsonl`. Started-but-unobserved requests are never automatically repeated.
- `python -m eval.run_final_mixed_regression summarize` and `python -m eval.render_final_mixed_regression` regenerate reports from saved results without paid model calls.
- Original 120/200/300 reports, timeout diagnosis, repair report, valid authoring provenance, LICENSE and attribution remain preserved.

## Release Acceptance

Post-evaluation pytest: **133 passed, 2 warnings**. Project stop/start, Streamlit homepage and FastAPI docs/health checks passed. Browser: **PASS — manually verified by user**, not automated browser testing. See [release acceptance](docs/QUERYMATE_V1_2_RELEASE_ACCEPTANCE.md) for scope, cleanup provenance and release conditions.
