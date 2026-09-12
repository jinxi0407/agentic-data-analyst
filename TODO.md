# Agentic Data Analyst TODO

> 本文件基于当前代码审计（`eaafb84`）整理。当前实现是 PostgreSQL + CLI 的 NL2SQL 原型；后续目标为面向独立电商 MySQL 的 Single Agent 数据分析服务。以下为规划，不代表已实现。

## 当前基线

- 已有：LangGraph `StateGraph`、表级 schema retrieval、LLM SQL 生成、执行失败重试、CLI REPL、`MemorySaver` 进程内 checkpoint。
- 当前业务样例：`orders`、`order_items`；metadata 为 `core_table`、`core_field`。
- 目标业务库：`users`、`products`、`orders`、`order_items`、`refunds`。

## P0：安全与配置边界

- [ ] 将数据库地址、用户名、密码、LLM/embedding API key 移出源码，使用 `.env` + 类型化 Settings；提交 `.env.example` 与 `.gitignore`。
- [ ] 轮换已进入历史/源码的数据库凭据和 API key；禁止日志、异常和 API 响应输出 secret。
- [ ] 为 NL2SQL 创建只读、最小权限的 MySQL 数据库账号，限制到目标 schema。
- [ ] 新增 SQL Guardrail：只允许单条 `SELECT` / 受限 `WITH ... SELECT`；拒绝 DDL、DML、事务控制、存储过程、注释绕过和多语句。
- [ ] 对 SQL 做解析级校验，不以正则代替安全边界；校验表/列白名单、禁止系统 schema。
- [ ] 强制 `LIMIT`、查询超时、最大扫描/返回行数和结果大小上限；记录 query id 与审计摘要。

## P1：数据层与 Schema Retrieval

- [ ] 设计并初始化独立电商 MySQL schema：`users`、`products`、`orders`、`order_items`、`refunds`，补齐主外键、索引、金额/时区/退款状态约束及脱敏策略。
- [ ] 将 PostgreSQL 专用连接、DDL introspection、SQL prompt 与 repository 迁移为 MySQL 实现；避免业务代码直接依赖驱动。
- [ ] 抽象 `DatabaseAdapter` / `SchemaRepository`，统一连接池、只读执行、超时、事务和错误归类。
- [ ] 将 schema metadata 的向量、版本、数据源、表/列描述与 checked/visibility 策略规范化存储。
- [ ] 支持全量/增量 schema indexing、幂等更新、schema fingerprint 与变更检测。
- [ ] 检索从当前“表注释 embedding + Python 全表余弦扫描”演进为可配置的 schema retrieval，并保留 deterministic top-k、阈值、召回 trace。
- [ ] 仅向 LLM 暴露命中的表、列、主外键关系、枚举值说明及安全约束，避免 schema 泄漏与 prompt 过长。

## P2：Single Agent 与 LangGraph

- [ ] 定义新的 `GraphState`：request/session 标识、原问题、解析意图、schema candidates、validated SQL、SQL plan、execution result、Pandas artifact、retry/error、trace 和最终回答。
- [ ] 将现有节点拆分为明确职责：request validation → schema retrieval → SQL planning/generation → SQL guardrail → execution → result analysis → response。
- [ ] 加入结构化的 Self-Correction：只对可修复 SQL 错误在限制次数内重试，并携带最小化错误信息；不可修复错误安全终止。
- [ ] 为复杂分析设计 Skills registry：`schema_retrieval`、`sql_query`、`result_analysis`、`pandas_analysis`；不引入 Multi-Agent、A2A、MCP 或额外向量数据库。
- [ ] 建立 lightweight agent harness：统一 tool contracts、输入输出 schema、错误分类、timeout、trace 和可测试的依赖注入。
- [ ] 明确多轮语义：会话只保存必要上下文与已确认分析意图，不把历史 SQL 或大结果无界累积进 prompt。
- [ ] 在 production runtime 使用可持久化 session/checkpoint 后端；保留 `MemorySaver` 仅用于 unit test/local fallback。

## P3：Pandas 与结果表达

- [ ] 增加受控 Pandas Tool，仅接收本次已执行 SQL 的受限结果集，不允许文件系统、网络或任意 Python 执行。
- [ ] 支持聚合、同比/环比、Top-N、分组、缺失值与时间序列等确定性分析，并保留输入 SQL/result provenance。
- [ ] 将 CLI `print` 输出改为结构化 `AgentResponse`：answer、table/summary、executed SQL、sources/schema trace、warnings、error、latency。
- [ ] 对金额、日期、百分比、空结果和敏感字段做统一展示与脱敏。

## P4：FastAPI 服务化

- [ ] 新增 FastAPI app factory、health/readiness、版本化 API 与 Pydantic request/response models。
- [ ] 提供同步查询接口；确认真实流式需求后再设计 SSE/WebSocket，不将 CLI 输出直接暴露为协议。
- [ ] 接入 request id、结构化日志、错误映射、CORS、认证/授权、速率限制与并发/队列保护。
- [ ] 禁止 API 返回原始数据库异常、连接信息、LLM key、完整内部 schema 或未脱敏 PII。

## P5：质量、评测与交付

- [ ] 建立 fixtures：电商 MySQL schema、代表性数据、schema metadata 和可重复 embedding/LLM mock。
- [ ] 单元测试：schema retrieval、SQL extraction、SQL guardrail、MySQL adapter、retry routing、state transitions、Pandas tool。
- [ ] 集成测试：合法查询、空结果、跨表 join、退款分析、SQL 失败自纠、超时、恶意 SQL、权限拒绝。
- [ ] 建立冻结的 NL2SQL evaluation set，标签至少覆盖 intent、required tables/columns、SQL safety、execution success、result correctness；区分开发集与 holdout。
- [ ] 记录评测版本、数据库 snapshot/schema fingerprint、模型版本、prompt/guardrail 版本和随机种子；不得用 holdout 逐题调参。
- [ ] 增加 CI：format/lint/type check/test、secret scan、依赖锁定、license/security review。
- [ ] 更新 README：以实际实现为准，说明当前 PostgreSQL 原型状态和 MySQL Agent 路线，提供不含 secret 的本地启动步骤。

## 明确保留与暂缓

- [ ] 保留并重用：`StateGraph` 编排思路、schema metadata 概念、Top-k schema 检索、错误反馈式 SQL 重试、repository 查询模式。
- [ ] 后续替换：源码硬编码配置、PostgreSQL 专用实现、CLI-only 输出、字符串 embedding 存储、无 SQL guardrail 的直接执行。
- [ ] 暂不引入：Multi-Agent、A2A、MCP、Milvus、Qdrant、Elasticsearch。
