# 常规单歧义澄清同集评测

## 结论与范围

Baseline = **同配置关闭澄清**；Final = **开启一次澄清后使用相同查询引擎**。
同集结果准确率 59.17% (71/120) → 73.33% (88/120)，差值 +14.17 pp。
这不是历史v1.0成绩的复测，也不和旧120题的39.17%/51.67%拼成提升。

120条自建合成冻结测试：60明确、60单歧义（时间20、指标20、筛选/实体20）。
覆盖常规过滤、单指标聚合、Top-K、日期及必要JOIN，不代表所有真实企业查询。
作者接触过Gate，未实现独立生成隔离，不宣称外部独立盲测。
模板族与旧集重叠审查见eval/SCOPED_DATA_REVIEW.md；部分同族参数化题相关，
不能当作120名独立现实用户抽样。两条替代意图当前结果相同，均保留，没有按结果删题。

**建议：保留可选澄清，默认关闭。** 本轮仅在固定合成范围检验交互价值；
真实联调存在补充格式/证据校验失败，且新增模型调用有延迟成本，不足以声称稳定适用于所有输入。
明确题变化 -11.67 pp；下面逐项给出实际退化/改善，不用Gate分数掩盖查询失败。

## 冻结与公平性

- 历史审计起点：02ce129；旧v1.0.0、引擎、Gate、数据、结果及修正证据保留。
- 候选共享代码提交：7cb7afc98d9172846dda825ad6bce4ae9d9c75b3。
- 题目、Reference SQL、GT及文件哈希冻结提交：f39717564e06a24eac83971b3d3ab475fb08f486。
- manifest SHA256：5068964b542a9e0cf948772c7eb64a03bbb8896276e305f490de1bf9b340f129。
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
| 全集结果 | 59.17% (71/120) | 73.33% (88/120) |
| 明确题结果 | 100.00% (60/60) | 88.33% (53/60) |
| 全部歧义题结果 | 18.33% (11/60) | 58.33% (35/60) |

- Final全集严格交互成功：72.50% (87/120)。
- Final全部歧义题严格交互成功：56.67% (34/60)。
- 有效澄清且补充被接受/核验子集的结果准确率：97.14% (34/35)，不能替代60条歧义总分母。
- 交互阶段计数：{"triggered": 56, "answer_available": 54, "answer_unavailable": 2, "followup_gate_proceed": 35, "answer_usage_verified": 35}；该子集要求答案使用核验，不等同于全部触发澄清的题目。
- 明确题严格成功要求未发生不必要澄清且结果正确；歧义题要求有效反问、正确使用补充并一次内取得正确结果。
- 未澄清碰巧答对只计结果，不计歧义严格成功。对中断缺失耗时不填0，另列缺失计数。

## 澄清决策

- Decision Accuracy：89.17% (107/120)
- Precision：96.43% (54/56)
- Recall：90.00% (54/60)
- F1：93.10% (108/116)
- 不必要澄清率：3.33% (2/60)
- 漏澄清率：10.00% (6/60)

| 标签 | 首轮实际决策 | 数量 |
|---|---|---:|
| clear | proceed | 53 |
| clear | invalid_output | 5 |
| clear | clarify | 2 |
| ambiguous | clarify | 54 |
| ambiguous | needs_rephrase | 3 |
| ambiguous | system_error | 1 |
| ambiguous | proceed | 2 |

首轮异常/无法继续：{"invalid_output": 5, "system_error": 1, "needs_rephrase": 3, "unsupported": 0}。
Final任务终态（含补充轮）：{"success": 90, "invalid_output": 23, "simulated_answer_unavailable": 2, "needs_rephrase": 4, "system_error": 1}。
明确invalid/system_error既不算TN也不算FP，但在Accuracy分母内算失败；歧义异常属于未clarify，计FN。
decision=proceed之后SQL失败仍是放行决策，但结果准确率为失败，不能混为一项指标。

## 配对与明确题回归

全集逐题配对：{"both_right": 62, "baseline_right_final_wrong": 9, "baseline_wrong_final_right": 26, "both_wrong": 23}。
明确题配对：{"baseline_wrong_final_right": 0, "baseline_right_final_wrong": 7, "both_right": 53, "both_wrong": 0}。
配对以结果正确为标准，不将来自不同问题的分数直接相减代替逐题对照。
所有逐题结果、失败和参考答案完整保存；没有只展示成功case。

## 系统耗时与调用成本

| 阶段 | 平均秒 | P50秒 | P95秒 | 有记录任务数 |
|---|---:|---:|---:|---:|
| Baseline总耗时 | 1.793 | 1.744 | 2.664 | 120 |
| Final首轮 | 7.62 | 4.839 | 8.467 | 120 |
| Final总耗时 | 11.436 | 7.497 | 15.785 | 120 |

| 系统 | 模型调用总数 | 平均调用/题 | 已返回usage输入Token | 已返回usage输出Token | 缺失usage调用 |
|---|---:|---:|---:|---:|---:|
| Baseline | 125 | 1.042 | 277331 | 5520 | 0 |
| Final | 299 | 2.492 | 658976 | 34770 | 1 |

耗时不包含模拟用户审核/思考、阶段间等待；包括本系统schema查询、模型、SQL和有限格式/执行修复。
tokens来自接口usage，不是字符数估算。缺失usage不视为真正零用量；未按未核实单价推算人民币账单。
“不额外重试”指评测层：保留现有SDK默认300秒请求超时，以及连接池ConnectionError的一次内部重试，
两版完全相同。调用次数统计generate_text/Generation.call逻辑调用，不等同于网络层重发次数；
没有将模型格式、SQL或结果错误当作网络异常免费重跑。网络等待亦保留在时延中。
上下文元数据缓存两版共享，按同一进程运行；模型端缓存及服务负载可能造成非确定性时延。

## 失败与已知限制

- scoped-013：统计家用电器已经下架的商品款数，只返回数量。 首轮=invalid_output，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-015：拉萨客户中各等级分别有多少人？只返回等级和人数。没有记录也正常。 首轮=invalid_output，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-020：南京每个客户等级的VIP人数分别是多少？只统计VIP，返回等级和人数。 首轮=invalid_output，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-035：厦门客户各等级分别有多少人？只返回等级和人数。 首轮=clarify，最终=simulated_answer_unavailable，结果正确=False，答案核验=False。
- scoped-040：武汉每个客户等级的VIP人数分别是多少？只统计VIP，返回等级和人数。 首轮=invalid_output，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-055：青岛客户各等级分别有多少人？只返回等级和人数。 首轮=clarify，最终=simulated_answer_unavailable，结果正确=False，答案核验=False。
- scoped-060：西安每个客户等级的VIP人数分别是多少？只统计VIP，返回等级和人数。 首轮=invalid_output，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-063：近期有效订单客单价是多少？只要金额。 首轮=clarify，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-065：最近销售额最高的两种支付方式，返回支付方式和有效订单销售额，同额按支付方式升序。 首轮=clarify，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-069：近期银行卡支付的有效订单销售额是多少？只返回金额。 首轮=clarify，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-072：近期购买手机数码的有效订单客户有多少人？去重，只返回人数。 首轮=clarify，最终=invalid_output，结果正确=False，答案核验=False。
- scoped-073：促销那几天家用电器卖出了多少件？按有效订单销量统计，只要件数。 首轮=clarify，最终=invalid_output，结果正确=False，答案核验=False。

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

联调记录：{"api_health": 200, "ui": 200, "direct_http": 200, "direct_status": "success", "first_http": 200, "first_status": "needs_clarification", "followup_http": 200, "followup_status": "invalid_output", "followup_preserves_original": false, "guardrail_write_blocked": true, "db_read_only_account": true}。
API /health、UI与直接查询正常；该次真实补充返回invalid_output，未执行查询，如实保留失败，未免费重跑。
API存在历史兼容入口/api/query；新同配置对照及UI使用/api/scoped-query（mode=direct/clarify）。
UI保留原布局与一键启停，仅增加可选开关。启动脚本校验PID归属；MySQL保持运行，未操作金融/EduRAG资源。
最终离线测试及结束时服务状态见eval/scoped_final_acceptance.json。
验收摘要：{"checked_at": "2026-09-14T14:07:38.943931+00:00", "pytest_exit_code": 0, "pytest_summary": "68 passed, 1 warning in 18.74s", "api_health": 200, "streamlit_health": 200, "streamlit_page": 200, "sdk_version": "1.27.5", "pydantic_version": "2.13.5", "fastapi_pid_owned": true, "streamlit_pid_owned": true, "mysql_health": "healthy", "mysql_port": "127.0.0.1:3307", "all_first_rounds_unchanged": true, "all_120_cases_present": true, "all_56_followups_complete": true, "frozen_files_and_database_unchanged": true, "historical_artifacts_unchanged": true, "api_ui_code_unchanged_since_freeze": true, "main_commit": "d9ba7eadb3a95f657ca391d2865a2b444dc99ae3", "v1_0_0_commit": "d9ba7eadb3a95f657ca391d2865a2b444dc99ae3"}。
完成后仅本地归档，不merge main、不创建Release tag、不push。

## 证据索引

- eval/scoped_clarification_freeze.json / scoped_run_freeze.json：系统、数据、参考日、哈希和指纹。
- eval/scoped_clarification_cases.json / scoped_reference_validation.json：全部120题及Reference SQL实测。
- eval/scoped_reply_packet.json / scoped_reply_review.json / scoped_reply_freeze.json：按实际反问的模拟回答审计。
- eval/scoped_clarification_raw.json：全部原始调用、状态、usage及耗时。
- eval/scoped_clarification_per_case.json / scoped_clarification_bad_cases.json：全部配对结果和失败。
- eval/scoped_clarification_report.json：固定规则汇总。
- docs/SCOPED_DEVELOPMENT_LOG.md：仅两轮开发及未解决限制。
