# Final Mixed Clarification Evaluation

Status: completed once on the locally frozen dataset. No post-result Gate, Prompt, validator, schema, business-rule or question changes.

## Scope And Interpretation

This is a **self-built synthetic mixed evaluation**, not a representative sample of live requests. The fixed composition is **200 = 140 clear + 60 single-ambiguity**: 20 time, 20 metric and 20 entity/filter cases. ON can receive one extra, pre-frozen user answer after asking a matching clarification question. This measures **interactive task completion**, not model ability under equal information.

The old 300 cases are revealed regression/development evidence. The historical 120-case clarification study has a different purpose and dataset; its 59.17% -> 73.33% (+14.17pp) and F1 93.10% are not reused or combined with the new results.

## Resumed 300-Case Regression

| Metric | Historical ON | Optimized ON |
|---|---:|---:|
| Clarification trigger | 122/300 (40.67%) | 0/300 (0.00%) |
| First-turn result accuracy | 99/300 (33.00%) | 228/300 (76.00%) |
| OFF correct -> ON incomplete | 130 | 0 |

Reused OFF: **232/300 (77.33%)**. Fresh ON delta: **-1.33pp**. The saved OFF was independently re-scored and its engine/direct-path inputs, public model parameters, business/schema context, original dataset and database fingerprint were verified unchanged. No OFF calls were repeated.

Paired counts: OFF correct -> ON correct 228; OFF correct -> ON wrong 4; OFF correct -> ON incomplete 0; OFF wrong -> ON correct 0; OFF wrong -> ON wrong/incomplete 68. The incomplete count fell by **130**. There were 296 successful SQL workflows, four failed workflows, and **zero observed transport/API failures**. All 300 Gate decisions were proceed; no simulated answers were supplied.

| 300-case timing | OFF saved | ON fresh serial |
|---|---:|---:|
| Mean seconds | 2.759772 | 4.028097 |
| P50 seconds | 2.196696 | 3.407051 |
| P95 seconds | 6.876529 | 8.288846 |
| Average model calls | 1.08 | 2.08 |

OFF originally used four workers; the resumed ON used one. These latency figures are descriptive, not a controlled estimate of Gate overhead. Provider aliases/request dates also limit reproducibility. Zero triggers on revealed data do not establish recall on ambiguous requests. The earlier offline 122-trigger audit classified A genuinely unresolved = 2, B resolvable by contract/schema/time = 116, C defective output = 4; these remain diagnostic reviewer judgments, not new benchmark labels.

## Freeze And Data Provenance

- Gate freeze commit: `b8ffbe2c3b09bd82605086bbfbb24faca4a8771d`; implementation `8fb1e3a`.
- Dataset/evaluation commit before any candidate calls: `597d5f28d6c6727e28950373ad416903ea28909b`.
- Manifest SHA-256: `572d7e35bf2cff859973d1522c07fec7a2e0858ab78288085fb13d155885a486`.
- Reference date: `2026-09-12`; database seed `20260911`. The original 300-case generation seed `20260916` is not the database seed.
- Database table fingerprints, protected production hashes, dataset, runner, scorer and protocol hashes: `eval/final_mixed_freeze.json`.
- Models: qwen-plus and text-embedding-v4 unchanged; this production workflow performs no embedding requests. SQL temperature 0.05, Gate temperature 0, execution retry limit 2, existing Gate format retry limit 1.
- Both fresh modes use concurrency 1, alternate first-turn order by case, and share the same production engine/context/metadata/guardrail/retry/scorer. First turns precede a separately audited follow-up phase.
- Gate timeout remains 5s connect / 30s read; production SQL transport defaults are unchanged. No evaluation-level retries or repeat of completed calls. An infrastructure failure stops scheduling.

Independent authoring model inputs were restricted to the protocol, synthetic database schema/metadata and business contract. They did not contain the Gate prompt or historical failure outputs. Raw responses, rejected drafts and every pre-freeze correction are retained under `eval/final_mixed_authoring*`. The initial draft batch was stopped for repetition; those drafts were never candidate-tested. Local review corrected unsupported fields, duplicated aggregation, missing/incorrect ambiguity labels, ties, and reference SQL syntax before freeze. This is internal authoring/review, not an external independent benchmark.

Historical question/reference-only screening covered 1500 records; it never used their failed model outputs. Alias/literal-normalized and order/limit/round-insensitive structural screening found no unresolved exact-template matches at freeze. This does not prove semantic novelty: core business operators necessarily recur. References were executed read-only on the unchanged MySQL snapshot. All 24 legitimate empty reference results were retained. No question was changed after candidate execution began.

## Mixed Results

| Result accuracy | OFF Baseline | ON Final |
|---|---:|---:|
| All 200 | 69.00% (138/200) | 73.50% (147/200) |
| Clear 140 | 87.86% (123/140) | 89.29% (125/140) |
| Ambiguous 60 | 25.00% (15/60) | 36.67% (22/60) |

**Overall delta: +4.50pp.** Ambiguous-query delta: +11.67pp.
Clear subset: 0 OFF-correct cases became ON-wrong/incomplete; 2 OFF-wrong cases became ON-correct.

| Clarification measure | Value |
|---|---:|
| Decision accuracy | 84.50% (169/200) |
| Precision | 100.00% (29/29) |
| Recall | 48.33% (29/60) |
| F1 | 65.17% (58/89) |
| Unnecessary clarification / clear | 0.00% (0/140) |
| Missed clarification / ambiguous | 51.67% (31/60) |
| Strict ambiguous interactive success | 20.00% (12/60) |

Strict interactive success requires a triggered, answerable clarification, the exact frozen single-slot answer actually supplied, preservation of the original question/known constraints, quoted resolved information from that answer in the engine input, and a correct final SQL result. Its denominator is all 60 ambiguous cases, not just successfully clarified cases. Raw result accuracy may include coincidental correct answers without clarification; it is intentionally reported separately.

| Paired outcome | Count |
|---|---:|
| OFF correct -> ON correct | 135 |
| OFF correct -> ON wrong/incomplete | 3 |
| OFF wrong -> ON correct | 12 |
| OFF wrong -> ON wrong/incomplete | 50 |

| System processing cost | OFF | ON |
|---|---:|---:|
| Mean seconds | 3.102990 | 5.652058 |
| P50 seconds | 2.349155 | 3.838523 |
| P95 seconds | 8.039741 | 15.326706 |
| Average model calls | 1.100 | 2.300 |

Latency sums actual system processing across performed turns, excluding local answer review/simulated thinking and queue wait. Model calls count wrapper calls, including format/execution retries; hidden SDK wire retries are not separately observable.
Observed infrastructure failures: **0**. Decision counts: `{"proceed": 167, "clarify": 29, "invalid_output": 4}`.

## Answer Isolation And Failure Evidence

Candidate functions accept only the public question/reference date and mode. Neither Reference SQL, Ground Truth, intended full meaning nor should_clarify labels enter candidate requests. Follow-up review packets contain only the original question, actual Gate question and frozen single-slot answer. No answer is supplied for clear cases or an unrelated clarification. Slot-enum equality alone is not sufficient: a local reviewer must confirm the literal answer addresses the actual question. Reviews are frozen before follow-up requests.

- Complete immutable calls and outputs: `eval/final_mixed_events.jsonl`.
- Per-case results: `eval/final_mixed_per_case.json`; all failed/strict-failed cases: `eval/final_mixed_bad_cases.json`.
- Actual clarification eligibility decisions: `eval/final_mixed_reply_review.json`; review hashes: `eval/final_mixed_reply_freeze.json`.

### Failure Breakdown

| Ambiguity type | OFF correct / 20 | ON correct / 20 | Triggered / 20 | Strict success / 20 |
|---|---:|---:|---:|---:|
| time | 3 | 11 | 10 | 9 |
| metric | 10 | 8 | 5 | 1 |
| entity_filter | 2 | 3 | 14 | 2 |

The conservative Gate still missed **31/60** ambiguous cases, including four first-turn `invalid_output` records. Among the 29 follow-ups, 17 reached SQL success, four failed SQL workflows, and eight returned `invalid_output` (structured decision/validation failure, not a transport timeout). Only **12/29 (41.38%)** triggered cases achieved a correct final result, equivalent to **12/60 (20.00%)** strict interactive success across all ambiguity cases. Metric ambiguity results regressed from 10/20 to 8/20; that regression is retained, not hidden by the overall gain.

One actual question (`final_mixed_191`) gave refund-reason examples not present in stored metadata. The open-ended question could still be answered by the frozen valid reason. This remains an observed UX limitation, not a reason to edit the Gate.

Representative failures below are descriptive only; no resulting changes were made:
- `final_mixed_032` (clear): OFF correct=False, ON correct=False, ON status=success. 统计每个品类下已上架产品（is_active=1）的数量、平均上市年份和平均上市季度，并按品类升序排列。
- `final_mixed_035` (clear): OFF correct=False, ON correct=False, ON status=success. 列出所有已上架产品（is_active=1）中，上市年份为2025年的产品名称、品类、品牌、上市月份和销售单价（list_price），按上市月份升序、list_price降序排列，最多返回100行。 以上排序相同时，再按商品ID升序。
- `final_mixed_036` (clear): OFF correct=False, ON correct=False, ON status=success. 统计每个上市季度（按launch_date计算）中已上架产品（is_active=1）的平均售价（list_price）、平均成本价（cost_price）和逐商品毛利率的简单平均值（(list_price-cost_price)/list_price，保留四位小数），按上市季度升序排列。
- `final_mixed_144` (time): OFF correct=False, ON correct=False, ON status=success. 分析这一阵的支付方式构成：各方式有多少有效订单？只返回付款方式和单数，按方式升序，最多100行。
- `final_mixed_145` (time): OFF correct=False, ON correct=False, ON status=success. 最近注册的VIP用户都分布在哪些城市和等级？只返回城市、等级、人数，按城市和等级升序，最多100行。
- `final_mixed_146` (time): OFF correct=False, ON correct=False, ON status=success. 这段时间上架、现在仍在售的商品，按品牌和品类各有多少个SKU？只返回品牌、品类、SKU数，按品牌和品类升序，最多100行。
- `final_mixed_153` (time): OFF correct=False, ON correct=False, ON status=success. 统计过去一段时间内，各有效订单状态的有效订单数、已批准退款记录数，以及退款记录数/有效订单数（保留4位）。订单按下单日期、退款按退款日期分别落入该期间统计，退款仅取父单当前为有效状态的记录；只列有有效订单的状态。返回状态、两项数量、比率四列，按比率升序。 主排序值相同时，再按订单状态升序。
- `final_mixed_171` (metric): OFF correct=False, ON correct=False, ON status=failed. 这份临时售后汇总要看云栖品牌手机数码的一个整体占比，不限时间。报表尚未说明是先汇总退款额和有效销售额再相除，还是逐商品计算退款率后取简单平均。请给出一个比率，保留4位小数。
- `final_mixed_173` (metric): OFF correct=False, ON correct=False, ON status=invalid_output. 不限时间，统计至少买过一件松果品牌食品生鲜商品的有效订单，想看消费强度，但报表没说明按每单还是每位购买用户计算。只返回一个平均金额，保留2位小数；金额按符合条件订单整单实付计一次。

## Limitations And Final Checks

- Self-built synthetic questions and internal semantic review can introduce selection/label bias; results do not establish online-user performance.
- The shared frozen scorer matches SQL results, not mere successful execution. It ignores column aliases/permutation, respects ordered rows when specified, and uses absolute numeric tolerance 0.005. Small ratio differences or empty results can coincide even with different SQL semantics; the scorer was not changed.
- One frozen answer turn cannot resolve an unrelated question or multiple missing choices. Unanswerable follow-ups remain failures with the original denominator.
- Qwen floating model aliases, nonzero SQL temperature and network timing limit deterministic reproducibility. No reruns were used to pick a favorable result.
- Final pytest: **112 passed, 2 warnings**, 21.36s. Existing AnyIO and DashScope deprecations; evidence in `eval/final_mixed_test_evidence.json`.
- Production/Gate/Prompt/validator/schema/business/SQL engine hashes remained frozen; database data, historical benchmarks and scores were not edited.
- Preserved: `docs/GATE_TIMEOUT_DIAGNOSIS.md`, `FINAL_300_CLARIFICATION_REGRESSION.md`, `FINAL_CLARIFICATION_EVALUATION.md` and prior evaluation artifacts.
- Local evidence only. No main merge, push, new tag, resume-number update, additional optimization or Financial/EduRAG Docker action.
