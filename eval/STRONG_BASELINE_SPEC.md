# Strong NL2SQL Baseline Specification

The Strong Baseline is a traditional business-aware NL2SQL pipeline:

`Question -> Full Schema/Business Context -> qwen-plus SQL -> basic SQL safety -> MySQL execution -> error-only retry -> result`

Included and frozen before holdout generation:

- qwen-plus, MySQL 8 and SQL temperature 0.05.
- Complete schema names, column names/types, primary keys, foreign keys and relationships from `information_schema`.
- Basic business definitions for valid orders, sales, product sales, quantity, approved refunds, refund rate and paying users.
- Basic date semantics for explicit reference date, day/month windows and date grouping.
- Basic Top-K/Bottom-K, direction and limit instructions.
- Single-pass SQL generation with at most two retries caused only by SQL parsing/safety or database execution errors.
- SQLGlot single SELECT, single statement and maximum row safety; no semantic rewrite or verification.

Explicitly excluded:

- Skill routing and skill-specific prompts.
- Structured Query Plan, Query IR and multi-stage Agent decisions.
- Field-level dynamic schema retrieval.
- Semantic verifier/repair and grain-aware JOIN planning.
- Advanced ranking rules or benchmark-case rules.
- Pandas post-analysis, final-answer generation and complex Agent Harness loops.

The Strong Baseline is implemented only under `eval/`; production Final Agent files under `app/` are unchanged.
