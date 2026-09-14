# Strong Baseline v2 Specification

Flow:

`Question -> fixed alias normalization -> full static schema metadata + business/time/FK/ranking context + five generic examples -> qwen-plus SQL -> basic SQLGlot safety -> MySQL -> error-only retry (max 2) -> rows`

Added over Strong Baseline v1:

- Fixed table-purpose, column-meaning and enum metadata.
- Fixed vocabulary aliases for user/customer, product, sales amount, quantity, refund amount and order count.
- Five generic examples covering filtering/aggregation, time filter, Top-K/simple JOIN, refund Group By and monthly grouping.

Excluded:

- Skill routing and dynamic skill prompts.
- Query Plan, Query IR and field-level dynamic retrieval.
- Relation expansion, multi-stage decisions and Agent loops.
- Semantic verifier/repair, grain-aware planning and advanced correction.
- Pandas analysis and final-answer generation.

All context and examples are static and are frozen before Final Holdout v2 generation.
