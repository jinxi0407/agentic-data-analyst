# Daily Business: Baseline vs Final

Baseline: `agent-v1-baseline / 3d612dfc725e3654094c51aa542aa88d2a55c856`。Final: `agent-final-release / cfb1c626445f435bdfa8451a068c6496fdf9a179`。
端到端准确率提升：-17.20 个百分点。

| 指标 | Baseline | Final |
|---|---:|---:|
| 端到端结果准确率 | 92.80% | 75.60% |
| Easy | 94.40% | 88.00% |
| Medium | 94.00% | 60.00% |
| Hard | 80.00% | 76.00% |
| complex | 100.00% | 100.00% |
| filtering_aggregation | 98.67% | 100.00% |
| one_two_table_join | 89.47% | 31.58% |
| refund_customer_product | 100.00% | 76.00% |
| time_trend | 74.00% | 60.00% |
| top_k_ranking | 100.00% | 82.00% |
| Paraphrase（30 条交叉标记） | 86.67% | 56.67% |
| 平均端到端延迟 | 7.76s | 9.23s |

## 评测协议

250 条；Easy/Medium/Hard = 125/100/25。题型按 75/50/50/38/25/12 分配，口语题 30 条（12%）。
全部题目、Reference SQL、数据库执行得到的 Ground Truth 和标签在首次模型调用前提交冻结。两边各运行一次，每条完成即保存。
使用同一数据库快照指纹、qwen-plus、text-embedding-v4、2026-09-12 reference date、SQL temperature 0.05、final-answer temperature 0.2。
两边依次运行，各自 4 个并发任务；延迟为该并发条件下包含检索及最终回答的单题墙钟时间，不是串行性能测试。
分数要求 workflow success，并比较 SQL 实际结果。行列数一致；列别名不影响比较；统一列排列；数值绝对误差最多 0.005、无相对误差；排名和明确顺序题校验行序，其余按多重集合比较。
评分器与旧评测的 3% 数值容差不同，因此只比较本报告两边的新结果，不能直接与历史百分比比较。

## 真实执行修复

- Baseline: 执行错误 1 题，恢复执行 1 题，修复后结果正确 0 题；执行修复成功率 100.00%。
- Final: 执行错误 1 题，恢复执行 1 题，修复后结果正确 0 题；执行修复成功率 100.00%。

以上来自主评测实际 execute_sql 错误与后续执行轨迹，不把正常重新生成 SQL 当作故障修复；Guardrail 触发的重试另计，不混入执行错误分母。

## 局限

- 这是合成数据库上的内部日常业务评测，题目包含同类查询的不同参数组合，不等同于独立企业线上流量或外部专家盲测。
- 1–2 表主集刻意不覆盖复杂三表以上的金额重复聚合问题；不能用本分数证明该能力。
- null SUM 与 0、额外输出列、排名并列顺序和数值舍入均可能影响严格结果比较；失败题全部保留。
- Main 中未单独运行 Stress Benchmark；不将历史压力测试并入此次分数。
- qwen-plus 为服务别名；同参数仍有服务端随机性，当前结果是单次运行观测。

## 可审计文件

- `eval/daily_business_cases.json` / `daily_business_manifest.json`
- `eval/daily_baseline_results.json` / `daily_final_results.json`
- `eval/daily_baseline_report.json` / `daily_final_report.json`
- `eval/daily_business_bad_cases.json` / `daily_execution_repair_report.json`
- `eval/daily_safety_report.json`

## 发布结论

Final 达到 75% 目标下沿，但比同一评测上的 Baseline 低 17.20 个百分点，且 JOIN、Top-K、Time/Trend、Refund/Customer/Product 与 Paraphrase 均退化。
因此本次对照验收不推荐 `agent-final-release` 替代 Baseline；发布候选应保持 `agent-v1-baseline / 3d612df`。Final 分支及结果作为可审计实验保留。
