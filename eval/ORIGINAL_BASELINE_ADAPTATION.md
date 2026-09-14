# Original Open-Source Baseline Adaptation

Source: `woshixiaojunle/NL2SQL-Demo`, local Git commit `eaafb8426fee4905953ac52f0ed2cea0f333a0f6`.

Preserved behavior:

- LangGraph sequence: question embedding, table retrieval, schema build, prompt build, SQL generation, SQL execution.
- Table-level cosine retrieval, Top-3 tables, checked metadata only.
- Schema assembled from retrieved table fields and their existing comments.
- Execution errors are returned to the same SQL prompt, with at most two retries.
- MemorySaver and one independent thread ID per benchmark question.

Environment compatibility changes fixed before evaluation:

- PostgreSQL connection and syntax were changed to the project's MySQL 8 database and read-only application account.
- GLM-4 was changed to the configured `qwen-plus` wrapper.
- `qwen3-vl-embedding` was changed to the existing `text-embedding-v4` table and query vectors.
- The upstream 0.5 retrieval threshold was changed to this project's established `text-embedding-v4` threshold, 0.15. Top-3 behavior remains unchanged.
- SQL generation temperature was set to the shared benchmark value, 0.05.
- Hard-coded credentials were replaced by the current environment-based configuration.
- PostgreSQL-specific prompt wording and identifier quoting were changed to MySQL equivalents.
- The database account is SELECT-only, so generated SQL cannot change benchmark data. No SQLGlot guardrail is added to this baseline.

Excluded Final Agent capabilities:

- Business Metric Dictionary and strengthened Time Semantics.
- Skill Router, Query Plan, Structured Intent and grain-aware JOIN planning.
- Explicit FK/JOIN context, SQLGlot Guardrail, Pandas analysis, final-answer generation and Agent Harness controls.

The frozen Daily Business cases, Ground Truth, database fingerprint, reference date and strict result comparator are reused without modification.
