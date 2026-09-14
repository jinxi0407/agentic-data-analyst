# Final Holdout Evaluation Incident

During the Strong Baseline run, `final_holdout_195` raised a SQLGlot `ParseError` before the evaluator persisted the result. The shared runner incorrectly treated every uncaught exception as an infrastructure failure, so it left the case unfinished and invoked that one case again on checkpoint resume.

The first attempt was an incorrect model result because its generated SQL could not be parsed. The accidentally repeated attempt also produced an incorrect result under the frozen comparator. The Strong Baseline score therefore remains 117 / 250 (46.80%) whether the first or second attempt is counted.

The recorded 2.39s Strong average latency uses the persisted second attempt for this case because the first attempt latency was not stored. One out of 250 latency observations is therefore a resumed observation.

After both systems completed, the runner was fixed so only recognized transient connection/API errors are left unpersisted; other uncaught errors are persisted as failed cases. No system was rerun after this fix. Agent code, prompts, Holdout cases, Ground Truth and scoring rules were unchanged.
