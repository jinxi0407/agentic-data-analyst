# 两轮开发修复记录

历史起点02ce129；原v1.0引擎、旧Gate/production模块、原测试集和结果原样保留。
新入口为/api/scoped-query；历史/api/query兼容接口未改语义。中文UI使用新入口，默认关闭澄清。

## Round 1

依据已揭晓失败：城市字面值不一致、未显式保留槽位、格式错误、补充后仍猜测缺失字段。
新增共享只读同城元数据、严格结构化Gate、用户原话证据、单轮槽位补充与完整性检查。
复用原DashScope SDK，最小实测json_schema与json_object均HTTP200。采用strict JSON Schema。
官方说明：https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope
本机SDK Generation.call支持response_format参数，接口返回input_tokens/output_tokens用于成本记录。
旧查询引擎的generate_text默认参数、SQL温度、Prompt、retry和安全边界未改变。
新Gate格式或证据校验失败最多一次修复；网络失败不重跑、不输出内部异常信息。

4条真实开发样例：城市别名与上月销售额直接成功；时间问答拒绝有效日期区间；“随便”停止。
保存：eval/scoped_development_round1_smoke.json。单元测试64 passed。

## Round 2（最后一轮）

修复确定问题：回答给出起止日期，而反问只列“最近几天”，错误视为未回答。
把实际反问和用户回答放到独立对话轮，明确等价时间表达有效，保留原始约束。
不添加具体题目if/else，不针对新冻结评测调参。
4条已揭晓开发样例：时间补充成功；无效回答needs_rephrase；客户指标补充成功；
大额订单首轮needs_rephrase，没有第三轮调参，作为已知局限保留。
保存：eval/scoped_development_round2_smoke.json。

接入UI/API及追加原始engine_input字段只用于审计与传输，不改变NL2SQL算法。
本轮未运行oracle完整问题诊断，不将开发smoke结果作为正式准确率。
开始新120题正式运行后，不再修改Gate、Prompt、业务契约、题目、GT或评分逻辑。
