# Complexity-Aware Hybrid Final Evaluation

## Final Result

```text
Strong Baseline v2 = 73.67% (221/300)
Hybrid Final       = 71.33% (214/300)
Improvement        = -2.33 pp
```

The frozen Complexity-Aware Hybrid Final did not outperform Strong Baseline v2 on the new 300-case holdout. The result is reported unchanged. No router rule, threshold, pipeline, case, Reference SQL, or Ground Truth was modified after either formal run.

Both systems used holdout digest `a4100e72f9965f70888ebb2e9f8974feb3b2520ec7a39fec51744922ea34cbd3`.

## Accuracy

| Metric | Strong Baseline v2 | Hybrid Final | Hybrid minus Strong |
|---|---:|---:|---:|
| Overall | 73.67% | 71.33% | -2.33pp |
| Easy | 88.67% | 88.00% | -0.67pp |
| Medium | 55.83% | 57.50% | +1.67pp |
| Hard | 70.00% | 43.33% | -26.67pp |
| Filtering / Aggregation | 90.00% | 88.89% | -1.11pp |
| Top-K / Ranking | 86.67% | 86.67% | 0.00pp |
| Time / Trend | 41.67% | 38.33% | -3.33pp |
| 1-2 Table JOIN | 73.33% | 73.33% | 0.00pp |
| Refund / Customer / Product | 80.00% | 66.67% | -13.33pp |
| Complex | 40.00% | 40.00% | 0.00pp |
| Paraphrase (36 cross-tagged cases) | 63.89% | 61.11% | -2.78pp |

Both systems completed SQL execution for 300/300 persisted cases. Strong v2 averaged 0.087 execution retries per case; Hybrid averaged 0.110.

## Latency

| System | Average End-to-End Latency |
|---|---:|
| Strong Baseline v2 | 2.76s |
| Hybrid Final | 3.65s |

Both runs used four total workers. Hybrid used two isolated fast-path workers and two isolated agent-path workers; per-case latency was measured inside the selected path and excludes queue wait time.

## Hybrid Routing

| Route | Cases | Share | Accuracy | Average latency |
|---|---:|---:|---:|---:|
| Fast / Strong v2 | 272 | 90.67% | 73.90% | 2.51s |
| Agent / frozen Final | 28 | 9.33% | 46.43% | 14.71s |

Complexity score distribution:

| Score | Cases |
|---:|---:|
| 0 | 218 |
| 1 | 54 |
| 2 | 8 |
| 3 | 10 |
| 4 | 10 |

The fixed rule was `score <= 1 -> fast` and `score >= 2 -> agent`. Each question executed exactly one path; no result fusion or second-path fallback was used.

## Frozen Architecture

Hybrid flow:

`Question -> deterministic complexity router -> exactly one frozen path -> unified result`

The router reads only the question and records `selected_route`, `complexity_score`, and `routing_reasons`. It uses no LLM, benchmark category, difficulty, case ID, expected result, or Ground Truth.

The two selected implementations remained unchanged:

- Fast path: Strong Baseline v2 commit `4cf4bc0`.
- Agent path: Existing Final Agent commit `3d612df`.
- Hybrid Final freeze: commit `6c204f5`.
- Final Release Holdout 300 freeze: commit `4000bba`.

## Holdout Protocol

- The Hybrid router was frozen before the formal holdout was created.
- The holdout was generated with seed `20260916` and reference date `2026-09-12`.
- Difficulty was fixed at 150 Easy, 120 Medium, and 30 Hard cases.
- Categories were fixed at 90 filtering/aggregation, 60 Top-K, 60 time/trend, 45 JOIN, 30 refund/customer/product, and 15 complex cases.
- Thirty-six cases used normal conversational business phrasing.
- All 300 questions were unique, had zero exact question overlap with historical case files, and had non-empty MySQL-derived Ground Truth.
- Both systems used the same qwen-plus, text-embedding-v4 configuration, temperature 0.05, MySQL snapshot, strict comparator, timeout policy, and execution environment.
- Strict result scoring required matching rows and columns with numeric absolute tolerance 0.005; ordered cases also required matching row order.
- Strong v2 ran first, followed by Hybrid. Failure cases were not inspected until both runs completed.
- Infrastructure reruns: Strong v2 = 0; Hybrid = 0.

## Conclusion

The experiment does not support replacing Strong Baseline v2 with this frozen Hybrid as the overall release. Hybrid improved Medium accuracy by 1.67pp, tied Top-K, JOIN, and Complex, but regressed overall accuracy by 2.33pp and increased average latency by 0.89s. The frozen result is retained as a negative but useful architecture experiment; no Strong Baseline v3 or router retuning was performed.

## Audit Files

- `eval/HYBRID_FINAL_SPEC.md`
- `eval/hybrid_final.py`
- `eval/final_release_holdout_300.py`
- `eval/final_release_holdout_300_cases.json`
- `eval/final_release_holdout_300_manifest.json`
- `eval/run_final_release_holdout_300.py`
- `eval/final_release_holdout_300_strong_v2_results.json`
- `eval/final_release_holdout_300_strong_v2_report.json`
- `eval/final_release_holdout_300_hybrid_results.json`
- `eval/final_release_holdout_300_hybrid_report.json`

