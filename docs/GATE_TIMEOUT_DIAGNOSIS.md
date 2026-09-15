# Clarification Gate Qwen Timeout Diagnosis

## Scope And Checkpoint

- Local branch: `agent-gate-timeout-diagnostic`.
- WIP checkpoint: `f780857`, preserving all 11 pre-existing changed/new files, including interrupted logs. The starting branch was actually `main`, not a feature branch.
- No merge to main, push, tag, large regression run, new benchmark generation, production SQL-engine invocation or Docker operation in this diagnosis. Read-only database fingerprint checks were performed.
- No new model or embedding call. Chat remains `qwen-plus`, Gate temperature remains `0`.

## Finding

The reproducible failure is in the current Qwen strict structured-generation path for this Gate request, not a general inability to reach DashScope. Both original full Gate requests established connections but timed out before response headers, even with one worker. The SDK had previously exposed this as its default approximately 300-second read timeout.

Providing the original output schema explicitly in the messages removed the observed stall, but keeping server-side `json_schema` was **not sufficient for acceptance**: an intermediate 10-call test completed yet incorrectly returned `proceed` for all five ambiguous inputs. Those results are retained, not discarded.

The final compatibility fix uses `json_object`, explicitly supplies the exact existing Pydantic JSON Schema as an output-format instruction, and retains the existing strict local Pydantic models and validators. With identical business instructions, metadata and questions, the final 10 calls completed and produced all expected decisions.

This isolates an API/model structured-output compatibility failure at the observable request level. It does **not** establish the provider's internal decoder implementation bug or prove that all `json_schema` requests fail. No root cause is attributed to missing API credit, stale connections or general DNS failure without evidence. The earlier hypothesis that merely adding the word JSON solved strict-schema timeouts was insufficient.

The provider documents that JSON Object guarantees JSON but not a particular shape, hence the original local validation remains necessary. JSON Schema mode does not require a JSON keyword; JSON Object does. Output-token caps may truncate JSON, so this fix does not add one. [Official structured-output documentation](https://help.aliyun.com/zh/model-studio/qwen-structured-output).

## Ordered Diagnostic Evidence

| Test | Result | Total |
|---|---|---:|
| Existing wrapper, `只回复 OK` | HTTP 200, OK | 0.793 s |
| Original full Gate, `最近30天销售额是多少？` | Read timeout before headers | 30.194 s |
| Original full Gate, `最近销售怎么样？` | Read timeout before headers | 30.279 s |
| JSON Object without conveying full output schema | Two quick HTTP 200 responses, failed existing format validation | 2.287 s |
| JSON Object + original schema, clear | proceed | 1.558 s |
| JSON Object + original schema, ambiguous | clarify | 4.513 s |
| Strict schema + explicit schema in messages, clear control | proceed | 1.704 s |
| Intermediate strict-mode serial 10 | Transport 10/10, expected decisions only 5/10 | Preserved in `08_fixed_serial_10.json` |
| Final JSON Object serial 10 | Transport 10/10, expected decisions 10/10 | Mean 2.697 s |

For the minimal request, DNS/TCP/TLS connection took **0.174 s**, response headers arrived at **0.772 s**, and total wrapper time was **0.793 s**. These are non-streaming calls: header arrival is not a first-token streaming measurement.

All requests were serial. The original full requests had two messages, approximately **10,130-10,138 bytes**, and **8,413-8,417 message characters**. Schema, business-contract and static-metadata blocks were each injected once, not recursively repeated. Existing overlapping FK descriptions were not redesigned.

The final requests have two messages, approximately **10,200-10,208 bytes**, **9,237-9,241 characters**, and **2,222-2,225 actual input tokens** reported by Qwen. Rough character-based estimates in raw diagnostics are not tokenizer measurements. `stream=false`; `max_tokens` remains the server default. No SQL-generation input is changed.

## Final Serial Smoke

- Questions: alternating the two user-specified diagnostic questions, five repetitions each. This tests serial connection reuse, not ten independent business intents.
- Completed: **10/10**; expected decisions: **10/10**.
- Clear: **5/5 proceed**, mean **1.379 s**.
- Ambiguous: **5/5 clarify**, mean **4.016 s**.
- Overall mean: **2.697 s**, range **1.281-4.200 s**.
- Model calls: **10**; observed HTTP requests: **10**; newly established connections: **1**. Connection reuse did not fail in this short serial test.
- No format retries, transport retries or approximately 300-second stalls in this final group.
- This is not a load test, idle-connection longevity test, accuracy benchmark or proof of correctness on all 300 queries.

## Minimal Code Changes

1. `app/agent/scoped_clarification.py`: output-format compatibility and Gate-only connect/read timeout `(5, 30)`.
2. `app/tools/qwen.py`: optional keyword-only timeout passthrough. Callers omitting it, including production SQL generation, emit the original arguments unchanged.
3. `eval/conservative_gate_experiment.py`: concurrency 1, truthful timeout/format metadata, separate future output prefix, and stop after saving a transport failure. Existing attempt logs are untouched. This runner was **not run** for any benchmark in this task.
4. `tests/test_scoped_clarification.py` and `tests/test_gate_transport.py`: schema consistency, default SQL-call preservation, timeout and retry bounds, serial-runner regression coverage.
5. `eval/diagnose_gate_transport.py`: bounded serial diagnostics and read-only integrity/acceptance summary. Records only timing, schema-independent metadata and decision summaries, not complete sensitive payloads.

The decision Prompt constants, follow-up Prompt, business rules, initial/follow-up Pydantic models, validators, question preservation and execution flow remain AST-identical to the WIP checkpoint. Only output formatting and request transport changed. The production SQL `direct()` path and protected engine files are verified against the released snapshot; the shared wrapper is verified to differ only by the opt-in timeout parameter and its forwarding branch.

## Timeout And Retry Policy

- Gate: 5-second connect timeout, 30-second read timeout. These are network-phase limits, not a promise of a 35-second global wall-clock deadline.
- Production SQL: existing SDK timeout defaults unchanged.
- No extra retry loop was introduced. Installed DashScope 1.27.5 already retries `ConnectionError` once; a unit test confirms that bound. `ReadTimeout` is not automatically replayed, because the server may already have processed a POST.
- Existing Gate format repair remains at most one additional model call and is counted/chargeable. It is not treated as a transport retry; business decisions are not retried to get a preferred answer.
- No timeout increase, arbitrary output truncation, hidden benchmark replay or worker-level concurrency escalation.

## Acceptance And Next Step

Full pytest after final production changes: **87 passed, 2 warnings**, 17.87 seconds. Warnings are the existing Starlette/AnyIO deprecation and a DashScope Assistants deprecation exposed by the new offline SDK retry test. No SDK migration was performed.

Detailed evidence: `eval/gate_transport_diagnostics/01_minimal.json` through `09_json_object_serial_10.json`, plus `acceptance.json`. The acceptance script verifies unchanged Gate policy AST, database/benchmark fingerprints, unchanged SQL-engine defaults, and the final ten response records.

The transport smoke prerequisite is met. A future 300-case regression can resume with **concurrency 1**, a new truthful configuration record and preserved old logs; unobserved interrupted calls must not be silently presented as completed results. This task does not execute that regression, generate Mixed cases, restart API/UI services, freeze the Gate or publish a release. Await the user's next instruction.
