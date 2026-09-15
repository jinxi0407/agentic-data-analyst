# 评测与生产依赖入口

## 最终修复版回归

当前结果见根目录 `FINAL_MIXED_CLARIFICATION_REGRESSION.md`，OFF 142/200，ON 155/200。
这是已揭晓200题上的回归，不是新盲测。功能冻结269a441；两边串行、同模型、同库、同评分。
`final_mixed_regression_` 前缀保存独立freeze、run_freeze、events、reply_packet/review/freeze、
per_case、report、bad_cases、supplement。`run_final_mixed_regression.py`复用原评分，
`render_final_mixed_regression.py`从保存结果生成报告。不要删除检查点后重新调用已完成题目。
本次400个首轮和32次补充均完整保存。用户人工浏览器验收PASS，pytest 133 passed、2 warnings。

## 以下为历史证据说明

版本提示：后续澄清交互修复改变了 Gate 和第二轮 Schema。下面200题仍是原冻结版本证据，
不代表修复版成绩。原冻结哈希不修改；`querymate_release_audit offline` 只应在其对应旧版本使用。
本轮固定12题两次会话协议为 `clarification_interaction_regression.json`，
执行记录仅在忽略目录 `logs/clarification/interaction_regression/`，不是新的盲测。

本目录同时保留运行依赖和实验文件。`strong_baseline.py`、`strong_baseline_v2.py`
由正式 API 的查询流程导入，不能因为含 baseline 字样而删除。

## 当前200题证据

- `final_mixed_cases.json`：冻结问题、标准 SQL、Ground Truth 和预设补充信息。
- `final_mixed_freeze.json`：原始数据/代码哈希；历史路径与哈希不改写。
- `final_mixed_events.jsonl`：429个唯一已完成阶段，包含 OFF、ON 首轮和29次补充。
- `final_mixed_per_case.json`、`final_mixed_report.json`、`final_mixed_bad_cases.json`：评分、汇总与失败。
- `run_final_mixed.py`：原始运行器，本轮不重新运行。
- `scoring.py`：冻结结果比较规则。
- `final_mixed_authoring_revision_1/`：当前题库有效编制与审核证据。
- 同名前缀的补充回答审核包、审核结论及协议均保持原路径。
- `querymate_offline_verification.json`：本次不调用 Qwen 的逐题复算与冻结核验。

本次只改变 UI 默认入口。原 freeze 包含当时的 `ui/app.py` 哈希，**保留原值**，
不能把界面更新伪装成原始文件未变。精确复现当时全量文件应使用数据冻结提交 `597d5f2`；
当前发布核验脚本仅允许 UI 接线差异，其余冻结文件仍须完全一致。

```bash
.venv/bin/python -m eval.querymate_release_audit offline
```

以上只使用保存结果和原评分器，不调用模型、不访问数据库、不重新运行200题或300题。
不要将离线复算当作新的独立评测。

## 历史证据与归档

固定300题原题库、原 OFF/ON 结果及优化后 ON、120题历史、城市修正、指标审计、
超时诊断和所有安全/API/UI/评分测试均保留。
当前有效编制采用 revision_1；仅初次被拒绝且无依赖的 `final_mixed_authoring/` 草稿
从工作目录归档，不按模型成绩删文件。

逐项依据见[文件清单](../docs/QUERYMATE_FILE_INVENTORY.json)及
[执行记录](../docs/QUERYMATE_CLEANUP_RECEIPT.json)。原始文件仍保存在
`0bb12e4` 提交和已逐文件校验的仓库外归档中，未改写 Git 历史。
可先用 `git show 0bb12e4:eval/final_mixed_authoring/<原文件名>` 只读核对，按清单定位备份。

[完整报告](../FINAL_MIXED_CLARIFICATION_EVALUATION.md) / [历史文档索引](../docs/README.md)
