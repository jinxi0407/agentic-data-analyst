# v1.1.0 发布验收与说明

## 范围与发布原则

本次从 `feature/llm-clarification-gate` 的 `cd101de` 归档继续。
只修改 API 接线、UI 状态、启动脚本、测试和文档，不重新评测120题或300题。
已完成的自动化与真实 API 验收通过；**浏览器交互待人工确认**。
当前环境的浏览器发现结果为空，不能保存真实浏览器截图；AppTest 不替代浏览器交互。
按发布授权中无浏览器能力时明确标记的要求保留此项，不宣称页面已全量人工验收。
本文件记录已验收的内容；GitHub 推送、标签及提交同步结果以发布时的最终摘要为准。

## 本次集成变更

- `/api/query` 仅提供 question 时与 `/api/scoped-query` 一致，默认 `mode=direct`，进入冻结的 `scoped.direct`，不调用 Gate。
- 显式 `mode=clarify` 进入冻结的 `scoped.run_interactive`。API 继续支持已签发的旧 context 完成补充；不以旧 Gate 处理新默认请求。
- 统一返回原问题和引擎标识。异常安全返回，不输出服务配置或凭据。
- UI 开关默认关闭，名称为“启用一次主动澄清”；新问题清除旧补充输入和 payload。
- 一键脚本核验 UID、命令、启动时间、项目根目录及服务名。健康且运行文件/配置指纹一致时复用；变更后仅重启本项目已登记服务。
- 未知进程占用端口时拒绝启动，不杀未知 PID。日常启动不初始化或 seed 数据。

SQL 引擎、业务/时间语义、城市映射、Gate Prompt、引用校验、安全与重试逻辑均保持原样。
完整性检查见 `eval/v1_1_release_integrity.json`，原始评测证据全部保留。

## 自动化测试

命令：`.venv/bin/python -m pytest -q`。
本次最终结果：**74 passed, 1 warning in 22.31s**。
warning 为 Starlette TestClient 对 AnyIO BlockingPortal 旧别名的弃用提示。

覆盖默认不调用 Gate、默认请求兼容、明确/歧义分支、一次补充、无效回答和超时/格式失败安全停止、
SQL 安全、UI 不串题、健康服务复用及未知端口不杀进程。
Streamlit AppTest 检查实际组件树与会话流程，但不等于真实浏览器渲染、点击或截图验收。

修复过程保留事实：第一次集成测试为 1 failed、73 passed、2 warnings。
旧测试 mock 仍指向原入口，发生一次未 mock 的查询路径调用尝试，并暴露响应元数据缺失。
随后只修复接线元数据和测试 mock，新增全局未 mock 外部调用阻断；没有修改核心算法。
此记录不把第一次失败隐藏为全程一次通过，也不将其计入正式冻结评测。

## 一次真实联调

完整原始请求/响应及参考 SQL 见 `eval/v1_1_release_smoke.json`。
这是少量非 Holdout 验收，不是新的准确率评测；没有重复运行以筛选成功结果。
参考 SQL 仅用于事后只读比较，没有传入被测 API。

| 验收 | 实际结果 | HTTP往返耗时 |
|---|---|---:|
| 默认有效订单优惠总额 | success，与参考结果一致 | 1.715s |
| 默认浙江客户消费额 JOIN/Top-6 | success，与参考结果一致 | 2.143s |
| 澄清开启，明确的月度支付方式优惠统计 | success，无反问，与参考结果一致 | 7.367s |
| 指定支付方式优惠总额，反问后补充 | needs_clarification → success，与参考结果一致 | 5.178s + 6.347s |
| 选定客户等级，用户表示尚未决定 | needs_clarification → needs_rephrase，无SQL执行 | 4.107s + 6.457s |
| DELETE安全拦截 | 只调用 guardrail，已阻断，未送数据库执行 | 不适用 |

有效补充只回答实际被问的付款方式及时间范围，保留原优惠总额与有效订单条件。
限制：首轮对“历史有效订单”仍额外询问时间范围；这是过度澄清倾向，原样记录，不调整 Prompt。
无效回答的提示为“请重新提交完整明确的问题。”，没有猜测用户等级。
验收前后七张业务/元数据表指纹一致，没有 seed 或数据库写入。

## 服务与页面

- 启动：`bash scripts/start_local.sh`；停止：`bash scripts/stop_local.sh`。
- 重复启动实际复用 FastAPI PID 75094、Streamlit PID 75105，没有新增第二套进程。
- 停止后 8002、8502 均可重新绑定，MySQL 仍 healthy；随后启动恢复成功。PID 仅作本次观测，不是永久配置。
- MySQL 为 `agentic-data-analyst-mysql`，`127.0.0.1:3307 -> 3306`；未操作 Financial/EduRAG Docker。
- API：`http://127.0.0.1:8002/health`；文档：`http://127.0.0.1:8002/docs`。
- 页面：`http://127.0.0.1:8502/`；HTTP与 Streamlit health 可达。
- **浏览器交互待人工确认**：标题、输入区、默认关闭开关、补充区、SQL、结果表及错误提示需在真实浏览器中确认。

## 冻结数据与限制

沿用已保存的120题统计：结果准确率71/120（59.17%）到88/120（73.33%），净增17题、+14.17pp。
严格交互成功为87/120（72.50%）；全部歧义题为34/60（56.67%）。
明确题由60/60降为53/60；平均系统耗时1.793s到11.436s，平均模型调用1.042到2.492。
澄清判断Accuracy 89.17%、Precision 96.43%、Recall 90%、F1 93.10%，F1不是端到端准确率。
Final可以获得一轮用户信息，这是交互价值对比，不是等信息模型能力对比。
一次超时缺失usage；自建冻结数据不代表外部独立盲测或线上分布。
过度/漏澄清、格式/引用校验失败、SQL业务口径错误均仍可能发生，因此默认关闭澄清。

详见 `FINAL_SCOPED_CLARIFICATION_EVALUATION.md`、`CLARIFICATION_METRIC_AUDIT.md`、
`docs/CLARIFICATION_RESUME_FACTS.md`。旧300题73.67%及2.76s只作原版独立历史记录。

## 安全、来源与同步范围

发布前扫描本次新增历史的全部文件版本及工作树，检查本地实际凭据和常见Token/私钥格式，
只记录路径与计数，不输出secret；扫描不能证明不存在所有未知格式的敏感信息。
初次完整审计覆盖9个待推归档提交的164个不同文件版本，未发现secret或禁止上传路径；
88个冻结核心/数据文件与 `cd101de` 一致。提交前另核对最终暂存内容。
`.env`、`.env.broken`、`.venv`、`.run`、日志和数据库物理文件不提交。
`LICENSE` 与原 main 字节一致，保留 Apache 2.0；新增 `ATTRIBUTION.md` 说明原开源来源。
GitHub API 只读核实 `jinxi0407/agentic-data-analyst` 为 Private，未改变可见性。
仅允许向自己的 origin 推送 main 与 v1.1.0，保留旧标签，不 force push、不写 upstream。
