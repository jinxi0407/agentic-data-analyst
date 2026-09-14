# Strong Baseline v2 vs Final Agent

## Final Result

```text
Strong Baseline v2 = 72.40% (181/250)
Final Agent        = 68.40% (171/250)
Improvement        = -4.00 pp
```

On this newly frozen holdout, Strong Baseline v2 outperformed the frozen Final Agent by 4.00 percentage points. This result is reported unchanged; neither system, the benchmark, nor Ground Truth was modified after evaluation.

Both systems used frozen Holdout v2 SHA-256 `77cd33025e8de00c79258397b77acfa0544f1a6ef19f0602fd052b8a62f054f2`.

## Accuracy

| Metric | Strong Baseline v2 | Final Agent | Final minus Strong v2 |
|---|---:|---:|---:|
| Overall | 72.40% | 68.40% | -4.00pp |
| Easy | 69.60% | 70.40% | +0.80pp |
| Medium | 81.00% | 62.00% | -19.00pp |
| Hard | 52.00% | 84.00% | +32.00pp |
| Filtering / Aggregation | 74.67% | 77.33% | +2.67pp |
| Top-K / Ranking | 54.00% | 58.00% | +4.00pp |
| Time / Trend | 78.00% | 54.00% | -24.00pp |
| 1-2 Table JOIN | 89.47% | 92.11% | +2.63pp |
| Refund / Customer / Product | 80.00% | 56.00% | -24.00pp |
| Complex | 41.67% | 66.67% | +25.00pp |
| Paraphrase (30 cross-tagged cases) | 66.67% | 66.67% | 0.00pp |

Both systems completed SQL execution for all 250 persisted cases. Average execution retry was 0 for both.

## Latency

| System | Average End-to-End Latency |
|---|---:|
| Strong Baseline v2 | 2.29s |
| Final Agent | 6.53s |

Both formal runs used four concurrent workers. Strong Baseline v2 ends after SQL execution and returns rows. Final Agent additionally runs schema retrieval, skill routing, structured query planning, deterministic result analysis, and final-answer generation, so its latency measures a broader product workflow.

## Frozen Versions

- Strong Baseline v2: commit `4cf4bc0` (`STRONG BASELINE V2 FROZEN`).
- Final Agent: commit `3d612df` (evaluated from the unchanged frozen worktree).
- Final Holdout v2: commit `6dbd50e`, file `eval/final_holdout_v2_cases.json`.
- Holdout seed: `20260915`.
- Reference date: `2026-09-12`.
- Difficulty distribution: 125 Easy, 100 Medium, 25 Hard.
- Category distribution: 75 filtering/aggregation, 50 Top-K, 50 time/trend, 38 JOIN, 25 refund/customer/product, and 12 complex.
- Conversational paraphrase cases: 30.

## Strong Baseline v2

Strong Baseline v2 is a conventional business-aware NL2SQL pipeline:

`Question -> fixed alias normalization -> static full schema and business context -> qwen-plus SQL -> basic SQLGlot safety -> MySQL -> execution-error retry (max 2) -> rows`

Compared with Strong Baseline v1, v2 adds only:

- Fixed table-purpose, column-meaning, type, PK/FK, and enum metadata.
- Fixed vocabulary aliases for customer/user, product, sales amount, quantity, refund amount, and order count.
- Five frozen generic examples covering filtering/aggregation, time filtering, Top-K/simple JOIN, refund grouping, and monthly grouping.

It retains qwen-plus, temperature 0.05, full static schema context, basic Business Metric Dictionary, basic Time Semantics, explicit PK/FK relationships, ranking rules, single-pass SQL generation, basic SQLGlot safety, MySQL execution, and at most two execution-error retries.

It does not include Skill Routing, structured Query Plan/IR, field-level dynamic retrieval, relation expansion, multi-stage Agent decisions, semantic verification/repair, grain-aware planning, Pandas analysis, or final-answer generation.

## Final Agent Differences

The frozen Final Agent adds these capabilities over the conventional Strong Baseline v2:

- Skill Router and dynamic business-skill context.
- Field-level Schema Retrieval with related-table expansion.
- Structured Query Plan for metrics, dimensions, filters, ranking, limits, and required tables.
- Richer business, time, JOIN, ranking, and paraphrase guidance shared by generation and execution repair.
- LangGraph state and node tracing across routing, retrieval, planning, generation, safety, execution, analysis, and answer stages.
- Deterministic row analysis and a final Chinese business answer.

This frozen Final version does not include later experimental semantic-verifier, semantic-repair, or grain-aware-planner work.

## Result Interpretation

Final Agent was stronger on Hard (+32.00pp), Complex (+25.00pp), Top-K (+4.00pp), JOIN (+2.63pp), filtering/aggregation (+2.67pp), and Easy (+0.80pp). These gains are consistent with its planning and multi-stage workflow helping on structurally difficult questions.

Strong Baseline v2 was substantially stronger on Medium (+19.00pp relative to Final), Time/Trend (+24.00pp), and Refund/Customer/Product (+24.00pp). Paraphrase accuracy was tied. Because those categories contain many cases, the Strong v2 advantages outweighed Final's hard/complex gains and produced the 4.00pp overall lead.

The experiment therefore does not support claiming an overall Final Agent improvement over Strong Baseline v2 on this holdout. It does show that Final handles the hardest and most structurally complex slices better, while the simpler static pipeline generalizes better on several common business slices and is materially faster.

## Evaluation Protocol

- Strong Baseline v2 was frozen before Holdout v2 was generated.
- Final Agent remained frozen at `3d612df`; no Final source was changed.
- Holdout questions, Reference SQL, database-derived Ground Truth, difficulty, categories, and distribution were frozen at `6dbd50e` before either formal run.
- Exact question overlap with the two previous benchmark sets was zero.
- Both systems used the same qwen-plus model, temperature 0.05, MySQL snapshot, reference date, Ground Truth, runner, strict result comparator, timeout policy, and four-worker environment.
- Strict scoring required matching result rows and columns, with numeric absolute tolerance 0.005; ordered cases also required matching row order.
- All incorrect cases remain in the per-case result artifacts.
- Infrastructure reruns: Strong Baseline v2 = 0; Final Agent = 0.

## Audit Files

- `eval/STRONG_BASELINE_V2_SPEC.md`
- `eval/strong_baseline_v2.py`
- `eval/final_holdout_v2_cases.json`
- `eval/final_holdout_v2_manifest.json`
- `eval/final_holdout_v2_strong_v2_results.json`
- `eval/final_holdout_v2_strong_v2_report.json`
- `eval/final_holdout_v2_final_results.json`
- `eval/final_holdout_v2_final_report.json`

