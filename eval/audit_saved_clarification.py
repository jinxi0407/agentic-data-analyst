"""Audit archived results without executing either candidate."""

import json
from collections import Counter
from pathlib import Path

from eval.scoring import write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = json.loads((ROOT / "eval/clarification_corrected_per_case.json").read_text())
    decisions = Counter()
    differences = []
    for row in rows:
        decision = {"success": "proceed", "failed": "proceed", "needs_clarification": "clarify",
                    "clarification_unavailable": "invalid_output"}.get(row["first_status"], row["first_status"])
        decisions[("ambiguous" if row["should_clarify"] else "clear", decision)] += 1
        if row["should_clarify"] and row["interactive_correct"] and not row["triggered"]:
            differences.append({"id": row["id"], "question": row["question"],
                "unmet_conditions": ["no valid clarification", "no user answer obtained or used"],
                "note": "Result equality alone does not establish intended semantics; an empty result can also coincide."})
    findings = {
        "source_commit": "02ce1297a9f97ccbb24927faa4ce1354a1f432e9",
        "decision_counts": [{"label": k[0], "decision": k[1], "count": v} for k, v in decisions.items()],
        "result_vs_interaction_difference": differences,
        "failure_examples": [
            {"id": "holdout-0-1-a", "stage": "missed_clarification", "evidence": "Undefined sales performance proceeded without choosing amount vs quantity."},
            {"id": "holdout-0-6-a", "stage": "wrong_clarification_scope", "evidence": "Asked province; fixed persona specified city. Strict simulator could not answer; not an SQL error."},
            {"id": "holdout-0-9-a", "stage": "incomplete_followup_passed", "evidence": "Asked metric only, accepted quantity, invented seven-day period; intended 19 days was never supplied."},
            {"id": "holdout-1-9-a", "stage": "incomplete_followup_passed", "evidence": "Asked time only, then inferred amount without asking unresolved metric."},
            {"id": "holdout-0-2-a", "stage": "entity_storage_mismatch", "evidence": "Threshold supplied, but city='上海' instead of stored 上海市."},
            {"id": "holdout-0-7-a", "stage": "missing_business_definition", "evidence": "No clarification of launch-date threshold; SQL used an invented broad launch range."},
        ],
        "caution": "Failure stages overlap. Saved traces cannot prove every internal merge error or uniquely attribute all result mismatches. No GT/scorer change is justified by result mismatch alone."
    }
    write_json(ROOT / "eval/clarification_metric_audit.json", findings)
    detail = "\n".join(f"| {r['id']} | 未提出有效澄清、未获取或使用用户补充 |" for r in differences)
    (ROOT / "CLARIFICATION_METRIC_AUDIT.md").write_text("""# 历史澄清指标审计

来源：02ce129 归档的修正版 120 题结果；本审计不调用模型、不修改历史报告。

| 标签 | proceed | clarify | needs_rephrase/unsupported | invalid_output | system_error |
|---|---:|---:|---:|---:|---:|
| 明确 60 | 57 | 0 | 0 | 3 | 0 |
| 歧义 60 | 16 | 44 | 0 | 0 | 0 |

这是首轮决策表。follow-up 的 simulated_answer_unavailable 4 条属于模拟用户无法回答，不是 Gate 首轮异常。
3 条格式异常 ID：holdout-0-0-c、holdout-1-9-c、holdout-3-9-c。

Accuracy = (44+57)/120 = 84.17%；Precision =44/44=100%；Recall=44/60=73.33%；
F1=88/104=84.62%；不必要澄清=0/60；漏澄清=16/60=26.67%。
44+0+16+57=117，另有3条明确题格式失败，仍在 Accuracy 的120分母中。
所以不是一张覆盖120条的二分类2×2表：若把全部未澄清都当作TN，会错误地把3个异常计为正确。
历史数字无需改写，但原报告“严格成功”的实现只检查结果正确和触发澄清，
未独立证明澄清问对了、回答被正确使用。新协议必须显式验证这两项，不可沿用更强名称却不检查。

## 62 条结果正确与 56 条交互成功

37 条明确结果正确 + 25 条歧义结果正确 = 62/120。
歧义中仅19条先澄清，另外6条未澄清碰巧结果一致；37+19=56/120。

| case_id | 未满足的交互条件 |
|---|---|
""" + detail + """

其中 holdout-3-10-a 对不存在的深圳返回合法空集/零值，结果巧合不能证明已理解“规模”。

## 失败归因与边界

- 漏澄清16条；典型为“销售表现”“新品”“规模”以及一条多歧义问题。
- 问错范围：4条问省份而固定用户仅能提供城市，严格模拟策略造成无法作答；不能声称真人必然失败。
- 补充后仍不完整：holdout-0-9-a 仅补销量却猜最近7天；holdout-1-9-a 仅补时间却猜金额。
- 实体存储错误：holdout-0-2-a 已获得金额阈值，但 SQL 仍使用上海而非上海市。
- SQL生成错误与澄清错误会重叠：51条执行成功但结果不匹配，不能全部归因于一个模块。
- 没有证据表明用户答案整段丢失；原实现拼接答案，但未显式限制槽位或强制完整性。
- 先前48条城市字面值修正有独立授权和SQL证据，原版及修正记录保留。不存在城市的12题未替换。
- 零条、零值和NULL允许合法；目前未发现足以修改结果比较函数或进一步改GT的证据。

从本轮起，旧 dev 与这120条已揭晓题仅用于开发/回归诊断，不再称新盲测。
新旧题范围不同，不可拼成“升级提升”。本轮最多两轮有原因的通用开发修复。
详细机器记录：eval/clarification_metric_audit.json。
""", encoding="utf-8")


if __name__ == "__main__":
    main()
