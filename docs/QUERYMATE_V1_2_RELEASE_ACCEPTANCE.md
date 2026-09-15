# QueryMate v1.2 Release Acceptance

## Frozen Scope

- Functional freeze: `269a441`; regression protocol and isolated runner: `b41ca45`.
- Gate, schema, validators, clarification merge, business context, SQL engine, guardrail, retries, database, dataset and scorer were not modified after freeze.
- `eval/final_mixed_regression_freeze.json` records the source hashes, original dataset hash, database fingerprints, reference date and identical model configuration.
- Release is conditional on final secret scan and normal Git synchronization; no force push or upstream push is permitted.

## Browser

**PASS — manually verified by user**. This is not automated browser testing.

The user confirmed: clear questions execute directly; missing city prompts a question; answering 南京市 continues to SQL and results; unspecified ranking performance prompts for a metric; 按销售金额 continues; explicit sales amount/quantity does not repeat the metric question; new questions do not inherit prior clarification state.

## Regression and Tests

- Existing disclosed benchmark: 200 cases, clear 140 and single ambiguity 60. No new questions or Ground Truth changes.
- Fresh OFF 142/200 (71.00%); ON 155/200 (77.50%); +6.50pp.
- 400 first turns and 32 reviewed follow-ups completed; infrastructure failures: 0.
- Full pytest after model evaluation: **133 passed, 2 warnings in 17.39s**.
- Warnings concern existing Starlette/AnyIO and DashScope deprecations; no paid calls are made by ordinary tests.
- Local port binding tests passed in the normal local environment; the former sandbox binding restriction is not a current test failure.
- Full results, failure cases, denominators, paired outcomes and latency are in [the regression report](../FINAL_MIXED_CLARIFICATION_REGRESSION.md).

## Runtime

- `bash scripts/stop_local.sh`: PASS; only recorded project API/UI processes stopped, MySQL left running.
- `bash scripts/start_local.sh`: PASS; own MySQL healthy, FastAPI and Streamlit started successfully.
- `http://127.0.0.1:8502/`, `http://127.0.0.1:8002/docs`, `/health`: HTTP 200.
- Both process ownership and runtime code fingerprints matched this project.
- No Financial/EduRAG Docker resource was modified; no volumes deleted or data seeded.

## Evidence and Cleanup

No additional evidence files were deleted in this final regression turn. Current dataset, both paired runs, manifests, scorer, runners, timeout diagnosis, interaction repair report, 300-case evidence, LICENSE and attribution are retained.

The previously staged cleanup in commit `5a95406` removed 42 rejected initial-authoring drafts from the working tree, not from history. These are preserved in commit `0bb12e4` and the verified external archive documented by `QUERYMATE_CLEANUP_RECEIPT.json` and `QUERYMATE_FILE_INVENTORY.json`. The valid `final_mixed_authoring_revision_1` provenance remains in the repository. No cleanup decision is based on accuracy or failure outcomes.

Old audit/smoke receipts retain their original-version scope. They are historical evidence, not replacements for the current tests or regression. Old 69.0% to 73.5% figures remain only in their historical report.

Secrets, `.env*` except `.env.example`, logs, PID files, virtual environments and Python caches stay ignored and are not release artifacts. Final synchronization is verified against origin/main and the peeled v1.2.0 tag after push.
