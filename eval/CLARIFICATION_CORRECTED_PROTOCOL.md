# Corrected Clarification Holdout Protocol

This protocol is fixed before either system is run on the corrected holdout.

- Systems: unchanged `30e9a08` application/Gate and v1.0.0 direct production engine.
- Data: 120 original holdout cases, 60 clear and 60 ambiguous. Only audited city literals
  and their database-derived reference results change. Dev corrections are archived but not rerun.
- Reference date: 2026-09-12. Chat model: qwen-plus; existing SQL temperature 0.05,
  Gate temperature 0. Same database fingerprint and runtime configuration throughout.
- Original datasets, manifests and correction proposal remain byte-identical.
- The existing `eval.scoring.compare` and `eval.run_clarification.report` remain unchanged.
- Neither system receives reference SQL, reference rows, labels, or benchmark resolved_question.
- Run v1.0 and v1.1 first turns once, checkpointing each result. Failed calls are retained.
- A separate reply review packet includes only original question, actual clarification question
  and the existing simulated user's available answer. No SQL, correctness score or reference data.
- A reviewer selects minimal verbatim answer segments that address the actual question.
  Extra conditions are withheld. If the available user answer cannot answer the question,
  the interaction is marked failed. Clear cases with no simulated answer cannot receive one.
- Freeze the selected replies before executing any follow-up. Only then run one follow-up.
- Rechecking ambiguity again produces needs_rephrase through the unchanged application.
- v1.1 receives one extra user information turn: this is an interactive task comparison,
  not equal-information model capability measurement.
- Report existing decision metrics, clear-query E2E, all-ambiguous task success, overall
  strict interactive success, and pure result accuracy for both systems.
- Successful-clarification subset means an originally ambiguous case whose user answer
  was supplied and whose second Gate returned proceed. Execution failures remain in its denominator.
- Report that subset's exact numerator/denominator, plus the answered subset separately.
- Latency is the sum of measured system calls, excluding manual review/user thinking/waiting.
- No post-result changes to system, prompt, questions, labels, answers, reference SQL or results.
- No merge, release tag or push. Produce FINAL_CLARIFICATION_EVALUATION.md and stop.
