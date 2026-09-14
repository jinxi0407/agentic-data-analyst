# Final Evaluation

**Baseline 38.00% → Final 92.80%，提升 +54.80pp。**

- Baseline：纯 Direct NL2SQL，95/250。
- Final：Agent v1 Strong Baseline (`3d612df`)，232/250。
- 两边使用同一套冻结的 250 条 Daily Business Benchmark、数据库快照、Ground Truth、reference date、qwen-plus、SQL temperature 和严格结果评分器。
- Direct 路径只使用完整 Schema 和原始问题生成一次 SQL；不使用 Schema Retrieval、Query Plan、Structured Intent 或 Repair。
- 固定 case SHA-256：`bbee0a6a6d6eb40b46f401aa21284585a90ae7fc4a98be2536e12934219e8294`。
