# QueryMate 文档索引

## 当前入口

- [本地澄清交互修复与24会话回归](CLARIFICATION_INTERACTION_REPAIR.md)：不是新的总体准确率，尚未发布。

- [项目说明与启停](../README.md)
- [200题完整评测及失败分析](../FINAL_MIXED_CLARIFICATION_EVALUATION.md)
- [评测目录与复现边界](../eval/README.md)
- [当前简历事实](CLARIFICATION_RESUME_FACTS.md)
- [发布验收记录](QUERYMATE_RELEASE_ACCEPTANCE.md)
- [逐文件分类、引用与备份清单](QUERYMATE_FILE_INVENTORY.json)
- [清理执行记录](QUERYMATE_CLEANUP_RECEIPT.json)
- [离线指标与冻结校验](../eval/querymate_offline_verification.json)
- [Gate 冻结记录](../eval/conservative_gate_final_freeze.json)
- [Qwen 超时诊断](GATE_TIMEOUT_DIAGNOSIS.md)

## 历史实验与审计

以下数据和报告保留原成绩及失败结论，不作为当前简历主指标：

- [300题原始回归报告](../FINAL_300_CLARIFICATION_REGRESSION.md)
- [优化后300题回归](../eval/conservative_gate_dev_transport_fix_report.json)：历史 OFF 为4 workers，当前 ON 为1 worker，耗时不可当作严格受控开销比较。
- [120题专项澄清评测](../FINAL_SCOPED_CLARIFICATION_EVALUATION.md)
- [较早澄清与标准答案审计报告](../FINAL_CLARIFICATION_EVALUATION.md)
- [城市取值修正审计](../eval/clarification_city_audit.json)
- [指标审计](../CLARIFICATION_METRIC_AUDIT.md)
- [v1.1 发布验收](V1_1_RELEASE_ACCEPTANCE.md)
- [原生产查询评测](../FINAL_EVALUATION.md)

所有已有历史分支、标签继续保留。首次被拒绝的题目草稿仅从工作目录归档，
仍可从已验证的仓库外备份和 `0bb12e4` 提交恢复，详情见清理记录。
