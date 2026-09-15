# Final Mixed Clarification Evaluation

**Status: INCOMPLETE. Gate is not frozen. No new mixed cases have been created or run.**

## Completed Work

- Starting production tag: `v1.1.0`, commit `2dc294fe43dc64658af7c85e7b60aae59a6be6a8`.
- Starting working branch: `main`, including the separate 300-case regression evidence.
- Gate-only changes: conservative first-turn decision, necessary missing slots, two distinct alternatives, insufficient-proof coercion to proceed, and removal of first-turn constraint re-quotation. Original question and existing follow-up context format are preserved.
- The production `direct()` function is AST-identical to the released version. Protected production engine, business dictionary, SQL prompts, guardrail, retry, metadata and scoring files pass the existing frozen-file check. Database fingerprint and original 300-case files were checked before each attempted run.
- Tests after the latest Gate change: **80 passed, 1 warning**, 15.44 seconds. Warning: existing Starlette/AnyIO deprecation.
- Existing API and Streamlit processes started successfully; FastAPI `/health` returned 200. MySQL was healthy on `127.0.0.1:3307 -> 3306`. Live model-backed clarification acceptance is still pending. Automated API/UI clarification regressions passed in pytest; this is not a claim of completed browser or live Qwen acceptance.

## Offline Audit

All 122 actual clarification triggers were reviewed individually against question, schema and existing business/time contract, without using Ground Truth to label ambiguity.

| Class | Count | Meaning |
|---|---:|---|
| A | 2 | Genuinely unresolved business definition: discount-rate denominator is not defined in the production contract. |
| B | 116 | Already resolvable from wording, business grain, schema or calendar rules; optional confirmation is not necessary clarification. |
| C | 4 | Defective alternatives/date arithmetic: impossible calendar date, equivalent alternatives, or incorrect computed start date. |

Per-case reasons and the original Gate output are preserved in `eval/conservative_gate_122_audit.json`. These are reviewer diagnostic judgments, not new benchmark labels. The 37 original `invalid_output` cases and 3 `needs_rephrase` cases are separate from the 122 triggers.

## Development Attempts

The old 300-case result is now **revealed regression/development evidence**, not a blind evaluation. Its trigger count is **122/300 (40.67%)**. Among historically OFF-correct cases, **130 became ON-incomplete**; **133 became ON-wrong or incomplete**. These are different measures and must not be conflated.

Attempt 1 introduced the compact structured schema and conservative instruction. Its first four requests ended in `transport_error` after approximately 300 seconds each. Four additional requests had already been scheduled when the run was interrupted. Their completion responses were not collected; their original `started` records remain intact. No semantic conclusion can be drawn from this attempt.

Isolated non-benchmark transport probes found:

- DNS and unauthenticated HTTP connectivity succeeded.
- A tiny authenticated Qwen request succeeded in 0.66 seconds.
- A short structured-schema request succeeded in 1.55 seconds.
- A complete Gate request with an appended explicit JSON instruction succeeded once in 1.80 seconds.
- Other complete Gate requests timed out, including a later probe after adding an explicit JSON instruction to the saved Prompt. Thus the successful isolated probe does **not** establish a resolved root cause.
- JSON-object mode without an explicit JSON instruction returned HTTP 400 `InvalidParameter` in a diagnostic-only process. Production response format was not changed.

Attempt 2 retained the same conservative policy and added the explicit JSON instruction. The first four requests remained pending and the run was interrupted to avoid scheduling further calls. No subsequent Gate tuning was performed. Both attempt logs and freeze snapshots are preserved under `eval/conservative_gate_dev_round{1,2}_*`; original historical artifacts were not overwritten. Attempt 1's runner hash intentionally identifies the earlier version of the new runner, before its output prefix was switched to attempt 2.

The new 300-case trigger rate, clear-query regression and OFF-correct-to-ON-incomplete reduction are **not available**. Pending calls must be accounted for as unobserved interrupted calls, never silently rerun or treated as successful answers. The two attempts are not complete evaluation rounds and must not be presented as accuracy results.

## New Mixed Evaluation

Only the protocol and a guarded, not-yet-executed independent authoring tool have been prepared:

- `eval/mixed_clarification_protocol.json`
- `eval/build_final_mixed.py`

Planned distribution: **200 cases = 140 clear + 60 single-ambiguity**. The ambiguous subset has 20 time, 20 metric and 20 entity/filter cases. This is a **self-built synthetic mixed evaluation, not the distribution of real online requests**.

The authoring tool refuses to run without a Gate freeze record. Its model input is restricted to protocol, business contract and database/schema metadata, with no Gate prompt or failure examples. Novelty review, reference SQL review, actual Ground Truth execution, file hashes and dataset freeze are all still required before either system can run. No candidate has seen a new mixed question.

All new mixed metrics remain **NOT RUN**: OFF/ON result accuracy, delta, clarification accuracy/precision/recall/F1, clear-query accuracy, ambiguous-query accuracy, strict interactive success, unnecessary/missed clarification, paired outcomes, latency and model calls.

The older 120-case interactive evaluation and 300-case first-turn regression serve different purposes; neither can substitute for the missing new mixed result. Historical values have not been reused as new scores.

## Release Boundary

No Gate freeze commit, new tag, push, resume-number update or final release has been made. No Financial/EduRAG resources were modified. Keep the current changes as unvalidated development work until complete Gate requests are reliably available; do not declare this evaluation or optimization accepted.
