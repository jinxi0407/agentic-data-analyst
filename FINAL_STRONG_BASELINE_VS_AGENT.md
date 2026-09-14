# Strong Baseline vs Final Agent

## Final Result

```text
Strong Baseline = 46.80% (117/250)
Final Agent     = 83.60% (209/250)
Improvement     = +36.80 pp
```

Both systems used frozen holdout SHA-256 `0242fc15886f4a34ff6803b94446db3a273559124ef8312230ed4f89d6c16649`.

## Accuracy

| Metric | Strong Baseline | Final Agent | Improvement |
|---|---:|---:|---:|
| Overall | 46.80% | 83.60% | +36.80pp |
| Easy | 55.20% | 69.60% | +14.40pp |
| Medium | 40.00% | 97.00% | +57.00pp |
| Hard | 32.00% | 100.00% | +68.00pp |
| Filtering / Aggregation | 65.33% | 84.00% | +18.67pp |
| Top-K / Ranking | 60.00% | 94.00% | +34.00pp |
| Time / Trend | 44.00% | 54.00% | +10.00pp |
| 1–2 Table JOIN | 13.16% | 92.11% | +78.95pp |
| Refund / Customer / Product | 20.00% | 100.00% | +80.00pp |
| Complex | 50.00% | 100.00% | +50.00pp |
| Paraphrase (30 cross-tagged cases) | 20.00% | 76.67% | +56.67pp |

Both systems completed SQL execution for 250 / 250 persisted cases. Average execution retry was 0 for both.

## Latency

| System | Average End-to-End Latency |
|---|---:|
| Strong Baseline | 2.39s |
| Final Agent | 6.35s |

Each system ran with four concurrent workers. Strong Baseline ends after returning SQL rows. Final Agent also performs schema retrieval, skill routing, query planning, deterministic row analysis and a second LLM call for the Chinese final answer, so this is product-pipeline latency rather than an isolated SQL-generation comparison.

## Strong Baseline Capabilities

The frozen Strong Baseline (`18872c5`) is a conventional business-aware NL2SQL system with:

- qwen-plus, MySQL 8 and SQL generation temperature 0.05.
- Complete table, column, data type, primary key, foreign key and relationship context from `information_schema`.
- Basic definitions for valid orders, order/customer sales, product sales, quantity, approved refunds, refund rate and paying users.
- Basic explicit-reference-date, recent-day/month and date-grouping semantics.
- Basic Top-K/Bottom-K direction and limit guidance.
- One SQL-generation stage followed by SQL execution.
- At most two retries caused only by SQL syntax/safety or database execution errors.
- SQLGlot single SELECT, single statement and maximum-row safety.

It does not contain skill routing, structured Query Plan/IR, field-level dynamic retrieval, semantic verification/repair, grain-aware planning, Pandas analysis or a decision loop.

## Final Agent Additions

Final Agent / Release v1.0 is the frozen `agent-v1-baseline / 3d612df` implementation. Compared with Strong Baseline, it adds:

- Skill Router for selecting the analysis behavior.
- Field-level dynamic Schema Retrieval plus relationship-table expansion.
- A structured lightweight Query Plan covering metric, dimensions, filters, ranking, limit and required tables.
- A richer Business Metric Dictionary, Time Semantics, FK/JOIN context and ranking semantics injected into SQL generation and execution-error repair.
- Paraphrase vocabulary and exact business category guidance.
- LangGraph state tracking and node trace across routing, retrieval, planning, generation, safety, execution, analysis and answer stages.
- Deterministic result analysis and a final Chinese business answer.

The Final measured here does not include later Structured Intent, semantic verifier, semantic repair or grain-aware planner experiments.

## Main Sources Of Improvement

- Refund / Customer / Product: +80.00pp (5/25 to 25/25).
- 1–2 Table JOIN: +78.95pp (5/38 to 35/38).
- Hard cases: +68.00pp (8/25 to 25/25).
- Paraphrase: +56.67pp (6/30 to 23/30).
- Medium cases: +57.00pp (40/100 to 97/100).
- Complex: +50.00pp (6/12 to 12/12).

Time / Trend remains the weakest Final category at 54.00%, despite a +10.00pp improvement. No post-result changes were made.

## Holdout Protocol

- Strong Baseline was frozen before Holdout generation.
- Final Agent was already frozen at `3d612df`.
- The new 250-case benchmark was then generated with seed `20260914` and frozen at commit `81bb499` before either formal run.
- Difficulty: Easy / Medium / Hard = 125 / 100 / 25.
- Categories: 75 filtering/aggregation, 50 Top-K, 50 time/trend, 38 JOIN, 25 refund/customer/product and 12 complex.
- Thirty cases (12%) use normal conversational business phrasing.
- Both systems used the same qwen-plus, text-embedding-v4 configuration, MySQL data fingerprint, reference date `2026-09-12`, questions, Reference SQL Ground Truth, strict result comparator and four-worker environment.
- All failed cases remain in the per-case result files.

## Evaluation Incident

One Strong case was accidentally invoked twice because an uncaught SQL ParseError was misclassified as infrastructure failure. Both attempts were incorrect, so no accuracy or category metric changed. The event and runner fix are documented in `eval/FINAL_HOLDOUT_EVALUATION_INCIDENT.md`; no model was rerun after the fix.

## Audit Files

- `eval/final_holdout_cases.json`
- `eval/final_holdout_manifest.json`
- `eval/final_holdout_strong_results.json`
- `eval/final_holdout_strong_report.json`
- `eval/final_holdout_final_results.json`
- `eval/final_holdout_final_report.json`
- `eval/STRONG_BASELINE_SPEC.md`
