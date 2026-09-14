# Original Baseline vs Final Agent

## Headline

**Original Open-Source Baseline 30.00% → Final Agent 92.80%，提升 +62.80pp。**

Direct NL2SQL Weak Baseline 为 38.00%，仅作为附加消融结果。

| 版本 | 正确题数 | End-to-End Result Accuracy |
|---|---:|---:|
| Direct NL2SQL Weak Baseline | 95 / 250 | 38.00% |
| Original Open-Source Baseline | 75 / 250 | 30.00% |
| Final Agent | 232 / 250 | 92.80% |

## Difficulty

| 难度 | Original Baseline | Final Agent | 提升 |
|---|---:|---:|---:|
| Easy | 55.20% | 94.40% | +39.20pp |
| Medium | 6.00% | 94.00% | +88.00pp |
| Hard | 0.00% | 80.00% | +80.00pp |

## Core Categories

| 类别 | Original Baseline | Final Agent | 提升 |
|---|---:|---:|---:|
| 1–2 Table JOIN | 0.00% | 89.47% | +89.47pp |
| Top-K / Ranking | 50.00% | 100.00% | +50.00pp |
| Time / Trend | 0.00% | 74.00% | +74.00pp |
| Paraphrase | 30.00% | 86.67% | +56.67pp |

## Latency

| 版本 | Average End-to-End Latency |
|---|---:|
| Original Open-Source Baseline | 3.13s |
| Final Agent | 7.76s |

两边依次运行，各使用 4 个并发任务。Original Baseline 返回 SQL 执行结果；Final Agent 的延迟还包含结果分析和最终中文回答，因此延迟差异不能解释为纯 SQL 生成性能差异。

## Original Baseline Capabilities

Original Baseline 从 `woshixiaojunle/NL2SQL-Demo` 的本地 upstream commit `eaafb8426fee4905953ac52f0ed2cea0f333a0f6` 恢复，保留：

- LangGraph 单 Agent 流程。
- Query Embedding。
- 表级余弦相似度检索，Top-3 表。
- 根据检索表的字段和注释动态构建 Schema。
- LLM SQL Generation。
- MySQL SQL Execution。
- SQL 执行错误回传给 LLM，最多重试两次。
- MemorySaver；每道评测题使用独立 thread ID。

环境兼容适配仅包括 PostgreSQL → MySQL、GLM-4 → qwen-plus、qwen3-vl-embedding → text-embedding-v4、安全环境变量配置、MySQL Prompt 语法，以及将原 0.5 检索阈值替换为项目对 text-embedding-v4 已固定的 0.15。数据库账号只有 SELECT 权限。完整记录见 `eval/ORIGINAL_BASELINE_ADAPTATION.md`。

Original Baseline 没有出现检索不到表：no-match 为 0 / 250；SQL 最终执行成功率为 100%，平均执行重试次数为 0.12。其准确率低来自可执行 SQL 的业务语义错误，而不是模型、Schema 或数据库被人为削弱。

## Final Agent Additions

Final Agent 在 Original Baseline 上增加：

- Business Metric Dictionary：统一有效订单、销售额、销量、退款金额和退款率等业务口径。
- 强化 Time Semantics：固定 reference date，明确最近 N 天/月、自然月和趋势口径。
- Skill Routing 与 Query Plan：先识别分析任务，再明确指标、维度、过滤、排序和限制。
- Schema Retrieval 增强：字段级检索并补齐关系所需表。
- 明确 FK / JOIN Context 与业务排名规则。
- SQLGlot SELECT Guardrail 与统一最大返回行数。
- Execution Repair、Agent Harness、Pandas 结果分析和最终中文回答。

Structured Intent 与 grain-aware JOIN 改造不计入本报告的 Final Agent；本报告的 Final 固定为 `agent-v1-baseline / 3d612df`，其已冻结结果为 232 / 250。

## Fairness And Reproducibility

- 两边复用同一套 250 条 Daily Business Benchmark、Ground Truth、数据库快照、reference date `2026-09-12` 和严格结果比较器。
- 两边均使用 qwen-plus、text-embedding-v4、SQL temperature 0.05 和 4 个并发任务。
- 固定 case SHA-256：`bbee0a6a6d6eb40b46f401aa21284585a90ae7fc4a98be2536e12934219e8294`。
- Original Baseline 只完整运行一次；所有 250 条逐题结果和失败 case 均保留。
- Final Agent、Benchmark、Ground Truth、数据库数据和 evaluation logic 未修改。

## Audit Files

- `eval/daily_original_baseline_report.json`
- `eval/daily_original_baseline_results.json`
- `eval/daily_baseline_report.json`
- `eval/daily_baseline_results.json`
- `eval/daily_business_cases.json`
- `eval/daily_business_manifest.json`
