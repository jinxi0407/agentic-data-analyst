"""Render the frozen evaluation output; never changes scores or reruns candidates."""

import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(name): return json.loads((ROOT/name).read_text())


def pct(value):
    return f"{value['percent']:.2f}% ({value['n']}/{value['d']})" if value['percent'] is not None else f"N/A ({value['n']}/{value['d']})"


def main():
    m=read('eval/scoped_clarification_report.json')
    rows=read('eval/scoped_clarification_per_case.json')
    freeze=read('eval/scoped_clarification_freeze.json')
    run=read('eval/scoped_run_freeze.json')
    smoke=read('eval/scoped_local_smoke.json')
    acceptance=read('eval/scoped_final_acceptance.json')
    raw=read('eval/scoped_clarification_raw.json')
    reviews=read('eval/scoped_reply_review.json')
    b=m['baseline'];f=m['final']
    gap=100*(f['overall']['n']/f['overall']['d']-b['overall']['n']/b['overall']['d'])
    clear_gap=100*(f['clear']['n']/f['clear']['d']-b['clear']['n']/b['clear']['d'])
    table='\n'.join(f"| {label} | {pct(b[key])} | {pct(f[key])} |" for label,key in [('全集结果','overall'),('明确题结果','clear'),('全部歧义题结果','ambiguous')])
    decisions='\n'.join(f"| {x['label']} | {x['decision']} | {x['count']} |" for x in m['decision_counts'])
    judging='\n'.join(f"- {label}：{pct(m[key])}" for label,key in [('Decision Accuracy','decision_accuracy'),('Precision','precision'),('Recall','recall'),('F1','f1'),('不必要澄清率','unnecessary'),('漏澄清率','missed')])
    lat='\n'.join(f"| {name} | {x['mean_s']} | {x['p50_s']} | {x['p95_s']} | {x['count']} |" for name,x in [('Baseline总耗时',b['latency']),('Final首轮',f['first_latency']),('Final总耗时',f['latency'])])
    cost='\n'.join(f"| {name} | {x['calls']} | {x['mean_calls']} | {x['input_tokens']} | {x['output_tokens']} | {x['missing_usage_calls']} |" for name,x in [('Baseline',b['usage']),('Final',f['usage'])])
    bad=[r for r in rows if not r['strict_success']]
    examples='\n'.join(f"- {r['id']}：{r['question']} 首轮={r['decision']}，最终={r['final_status']}，结果正确={r['final_correct']}，答案核验={r['answer_used']}。" for r in bad[:12])
    clear_pairs={key:sum(not r['ambiguous'] and r['pair']==key for r in rows) for key in ['baseline_wrong_final_right','baseline_right_final_wrong','both_right','both_wrong']}
    error_counts={k:sum(x['count'] for x in m['decision_counts'] if x['decision']==k) for k in ['invalid_output','system_error','needs_rephrase','unsupported']}
    outcomes=dict(Counter(r['final_status'] for r in rows))
    stages={'triggered':len(reviews),'answer_available':sum(x['valid_question'] for x in reviews),
            'answer_unavailable':sum(not x['valid_question'] for x in reviews),
            'followup_gate_proceed':sum(x.get('followup',{}).get('payload',{}).get('gate_decision',{}).get('decision')=='proceed' for x in raw.values()),
            'answer_usage_verified':sum(r['answer_used'] for r in rows)}
    report=f'''# 常规单歧义澄清同集评测

## 结论与范围

Baseline = **同配置关闭澄清**；Final = **开启一次澄清后使用相同查询引擎**。
同集结果准确率 {pct(b['overall'])} → {pct(f['overall'])}，差值 {gap:+.2f} pp。
这不是历史v1.0成绩的复测，也不和旧120题的39.17%/51.67%拼成提升。

120条自建合成冻结测试：60明确、60单歧义（时间20、指标20、筛选/实体20）。
覆盖常规过滤、单指标聚合、Top-K、日期及必要JOIN，不代表所有真实企业查询。
作者接触过Gate，未实现独立生成隔离，不宣称外部独立盲测。
模板族与旧集重叠审查见eval/SCOPED_DATA_REVIEW.md；部分同族参数化题相关，
不能当作120名独立现实用户抽样。两条替代意图当前结果相同，均保留，没有按结果删题。

**建议：保留可选澄清，默认关闭。** 本轮仅在固定合成范围检验交互价值；
真实联调存在补充格式/证据校验失败，且新增模型调用有延迟成本，不足以声称稳定适用于所有输入。
明确题变化 {clear_gap:+.2f} pp；下面逐项给出实际退化/改善，不用Gate分数掩盖查询失败。

## 冻结与公平性

- 历史审计起点：02ce129；旧v1.0.0、引擎、Gate、数据、结果及修正证据保留。
- 候选共享代码提交：{freeze['code_commit']}。
- 题目、Reference SQL、GT及文件哈希冻结提交：{run['data_commit']}。
- manifest SHA256：{run['manifest_sha256']}。
- 两版共享 qwen-plus、SQL temperature=0.05、execution retry=2、静态schema/FK、同城元数据。
- Gate temperature=0，当前DashScope接口实测支持strict JSON Schema；最多一次格式/证据修复。
- Embedding配置text-embedding-v4；本次静态查询引擎不调用embedding，不重复付费索引。
- 参考日期2026-09-12，业务时区Asia/Shanghai；七表指纹见eval/scoped_clarification_freeze.json。
- eval/scoring.py未改变：真实结果比较，非“SQL能执行”；数字绝对容差0.005，列别名可不同，
  指定排序时保留顺序，无序时多重集匹配，NULL与零区分，列数不能多出。
- 两版同一数据库、seed未改。候选函数仅接收原问题和参考日；不传GT/SQL/标签/标准完整问题。
- 正式串行运行，按题交替两版先后次序；断点保存开始与完成。无额外传输重试，未重跑失败模型case。
- Final有额外一次用户信息：衡量**交互任务价值**，不是等信息条件下模型能力。

## 历史指标审计

详见CLARIFICATION_METRIC_AUDIT.md。旧首轮明确proceed57、invalid3；歧义clarify44、proceed16。
Accuracy101/120=84.17%，Precision44/44=100%，Recall44/60=73.33%，F1=88/104=84.62%。
3个异常保留在总分母，不是覆盖120条的简单二分类2×2表。旧数字无需篡改。
62条结果正确中有6条歧义题未澄清而碰巧答对，因此旧“触发+结果”成功仅56条。
旧实现未独立验证问对和正确使用补充，本轮提前冻结更明确的交互定义，不倒改旧报告。

## 同集结果

| 指标 | Baseline | Final |
|---|---:|---:|
{table}

- Final全集严格交互成功：{pct(f['strict_overall'])}。
- Final全部歧义题严格交互成功：{pct(f['strict_ambiguous'])}。
- 有效澄清且补充被接受/核验子集的结果准确率：{pct(f['accepted_answer_subset'])}，不能替代60条歧义总分母。
- 交互阶段计数：{json.dumps(stages,ensure_ascii=False)}；该子集要求答案使用核验，不等同于全部触发澄清的题目。
- 明确题严格成功要求未发生不必要澄清且结果正确；歧义题要求有效反问、正确使用补充并一次内取得正确结果。
- 未澄清碰巧答对只计结果，不计歧义严格成功。对中断缺失耗时不填0，另列缺失计数。

## 澄清决策

{judging}

| 标签 | 首轮实际决策 | 数量 |
|---|---|---:|
{decisions}

首轮异常/无法继续：{json.dumps(error_counts,ensure_ascii=False)}。
Final任务终态（含补充轮）：{json.dumps(outcomes,ensure_ascii=False)}。
明确invalid/system_error既不算TN也不算FP，但在Accuracy分母内算失败；歧义异常属于未clarify，计FN。
decision=proceed之后SQL失败仍是放行决策，但结果准确率为失败，不能混为一项指标。

## 配对与明确题回归

全集逐题配对：{json.dumps(m['paired'],ensure_ascii=False)}。
明确题配对：{json.dumps(clear_pairs,ensure_ascii=False)}。
配对以结果正确为标准，不将来自不同问题的分数直接相减代替逐题对照。
所有逐题结果、失败和参考答案完整保存；没有只展示成功case。

## 系统耗时与调用成本

| 阶段 | 平均秒 | P50秒 | P95秒 | 有记录任务数 |
|---|---:|---:|---:|---:|
{lat}

| 系统 | 模型调用总数 | 平均调用/题 | 已返回usage输入Token | 已返回usage输出Token | 缺失usage调用 |
|---|---:|---:|---:|---:|---:|
{cost}

耗时不包含模拟用户审核/思考、阶段间等待；包括本系统schema查询、模型、SQL和有限格式/执行修复。
tokens来自接口usage，不是字符数估算。缺失usage不视为真正零用量；未按未核实单价推算人民币账单。
“不额外重试”指评测层：保留现有SDK默认300秒请求超时，以及连接池ConnectionError的一次内部重试，
两版完全相同。调用次数统计generate_text/Generation.call逻辑调用，不等同于网络层重发次数；
没有将模型格式、SQL或结果错误当作网络异常免费重跑。网络等待亦保留在时延中。
上下文元数据缓存两版共享，按同一进程运行；模型端缓存及服务负载可能造成非确定性时延。

## 失败与已知限制

{examples}

- Gate结构/引用校验能阻止伪造原文片段，但不能数学证明每个槽位语义归类正确。
- 原问题始终原样保留，补充仅取被问槽位原文；但底层SQL仍可能误解或遗漏条件。
- 严格成功核验包括实际反问审查、回答原文来源、槽位及已知约束保持、引擎实际收到补充，以及结果比较。
  结果相等仍不能证明SQL对所有可能数据库都语义等价，特别是空集或两个意图恰好同值时。
- 首轮可能过早needs_rephrase，或者漏问关键指标；格式错误失败关闭，安全但牺牲可用性。
- 此次首轮明确题5条invalid_output、2条不必要澄清，导致明确题60/60降到53/60；不是底层引擎在明确题普遍失效。
- 54条已回答任务中，35条补充被接受，18条invalid_output、1条needs_rephrase；不能用34/35遮盖这19条失败。
- scoped-119正确收到cash渠道，但底层SQL把客单价分母写成去重客户数而非订单数，执行成功仍判错。
  原业务字典app/business/metrics.py明确客单价为有效订单AVG(paid_amount)，因此不是本次GT错误。
  当前生产引擎使用的简化BUSINESS_CONTEXT未显式纳入这一公式；上下文覆盖仍不完整，本轮冻结后不补调。
- scoped-091未澄清指标而碰巧选对，结果计分为对，严格交互不计成功。
- scoped-075约300秒请求等待后system_error，未重跑，留在分母及耗时；该调用usage缺失，已知Token合计不是完整账单。
- 已逐题查看35条接受补充后的SQL。34条结果正确且未发现额外意图冲突；scoped-098/115经订单行关联商品，
  在当前固定快照上结果相同，但不能证明对任何未来含缺失关联的数据都等价。详见scoped_posthoc_semantic_review.json。
- invalid_output仅能确认结构或引用证据校验未通过；未保存每次原始校验错误详情，不能可靠分解到每个具体字段。
- 一轮用户补充有局限；剩余歧义不会开启无限追问。不将Gate-F1误写成端到端准确率。
- 实体元数据只做当前数据库经验证的同城市名后缀映射，不推断华东等地区；不存在城市保留合法空结果。
- 两轮开发后即冻结；没有因正式表现再调Prompt、系统、题目或GT，也不再生成更容易的新最终题库。

## 本地验收与交付

联调记录：{json.dumps(smoke,ensure_ascii=False)}。
API /health、UI与直接查询正常；该次真实补充返回invalid_output，未执行查询，如实保留失败，未免费重跑。
API存在历史兼容入口/api/query；新同配置对照及UI使用/api/scoped-query（mode=direct/clarify）。
UI保留原布局与一键启停，仅增加可选开关。启动脚本校验PID归属；MySQL保持运行，未操作金融/EduRAG资源。
最终离线测试及结束时服务状态见eval/scoped_final_acceptance.json。
验收摘要：{json.dumps(acceptance,ensure_ascii=False)}。
完成后仅本地归档，不merge main、不创建Release tag、不push。

## 证据索引

- eval/scoped_clarification_freeze.json / scoped_run_freeze.json：系统、数据、参考日、哈希和指纹。
- eval/scoped_clarification_cases.json / scoped_reference_validation.json：全部120题及Reference SQL实测。
- eval/scoped_reply_packet.json / scoped_reply_review.json / scoped_reply_freeze.json：按实际反问的模拟回答审计。
- eval/scoped_clarification_raw.json：全部原始调用、状态、usage及耗时。
- eval/scoped_clarification_per_case.json / scoped_clarification_bad_cases.json：全部配对结果和失败。
- eval/scoped_clarification_report.json：固定规则汇总。
- docs/SCOPED_DEVELOPMENT_LOG.md：仅两轮开发及未解决限制。
'''
    (ROOT/'FINAL_SCOPED_CLARIFICATION_EVALUATION.md').write_text(report,encoding='utf-8')
    facts=f'''# 可核验的澄清功能事实

- 在同一冻结120题自建合成常规澄清测试上，对比同配置关闭澄清与开启一轮澄清，
  结果准确率由{pct(b['overall'])}变为{pct(f['overall'])}，差值{gap:+.2f}个百分点。
- 测试范围仅60明确题与60单歧义题（时间20、指标20、筛选/实体20），不代表企业总体准确率或外部独立盲测。
- 升级版获得额外一轮用户信息，比较的是交互价值，不是等信息模型能力。
- 全部歧义题严格交互成功率{pct(f['strict_ambiguous'])}；明确题结果准确率{pct(f['clear'])}。
- 澄清F1={pct(m['f1'])}，这是决策指标，**不是端到端准确率**。
- 平均系统总耗时Baseline {b['latency']['mean_s']}秒、Final {f['latency']['mean_s']}秒，排除用户思考时间。
- 共用生产查询引擎、Qwen、数据库、实体上下文和评分；结构化Gate只填已询问字段，最多一次用户澄清，格式失败不默认执行。
- 保留SQL Guardrail和只读MySQL；实现中文双轮UI、可选开关与按PID归属的一键启停。
- 仍为可选澄清功能，不宣称全面更优；失败和耗时完整公开。不得拼接不同测试集分数为提升。

证据：FINAL_SCOPED_CLARIFICATION_EVALUATION.md及eval/scoped_clarification_report.json。
代码冻结{freeze['code_commit']}；评测数据冻结{run['data_commit']}。
'''
    (ROOT/'docs/CLARIFICATION_RESUME_FACTS.md').write_text(facts,encoding='utf-8')


if __name__=='__main__': main()
