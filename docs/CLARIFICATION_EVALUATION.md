# Clarification Evaluation v1.1

The frozen v1.0 engine remains unchanged. This experiment evaluates an LLM gate at temperature 0,
one user clarification turn and at most one format retry. SQL generation still uses qwen-plus
at temperature 0.05 and the same execution repair and result comparator.

## Protocol

- Development: 80 synthetic cases, 40 clear and 40 ambiguous; reference SQL executed read-only.
- Final holdout: 120 cases (60 clear, 60 ambiguous), designed and generated after the gate commit.
- Freeze questions, simulated user answers, reference SQL, database-derived results and hashes before model calls.
- Compare direct v1.0 and interactive v1.1 against the same intended answer on the same database.
- v1.0 receives only the initial question. v1.1 may receive the supplied user answer after a clarification.
- This measures the value of additional user information, not a model-only accuracy improvement.
- All model, parsing, SQL and result failures remain in the results; completed cases are not rerolled.
- Overall interactive success requires correct final results AND a clarification for ambiguous inputs.
- Pure result accuracy is also reported; a lucky guess on an ambiguous input is not interactive success.
- Post-clarification E2E uses all 60 intended ambiguous cases as denominator, including missed clarifications.
- An unexpected clarification on a clear question has no simulated answer and counts as failure.
- Latency excludes human thinking time and includes the gate, SQL generation, repair and database execution.
- No prompt changes follow holdout disclosure. The old 300-case score stays 73.67%, 2.76s.

## Development Results

Decision accuracy: 88.75%; precision: 100%; recall: 80%; F1: 88.89%.
Unnecessary clarification: 0%; missed clarification: 20%.
Clear-query result accuracy: 97.5%; post-clarification E2E: 80%.
Overall interactive success: 88.75%; pure result accuracy: 93.75%.
One service/format failure occurred and was retained. The original runner did not retain its
specific failure subtype; do not interpret it as confirmed model-format or confirmed network failure.
No gate prompt tuning was performed after these results.

The development fixtures use repeated business-intent families with varied values. They are
synthetic checks, not a representative sample of production users. Final results and limitations
will be added after the independently frozen holdout completes.
