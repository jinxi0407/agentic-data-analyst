# Complexity-Aware Hybrid Final Specification

Frozen routing flow:

`Question -> deterministic complexity router -> exactly one of Strong Baseline v2 or frozen Final Agent -> unified result`

Rules:

- Default route is `fast`.
- Each generic complexity feature contributes one point.
- `complexity_score <= 1` selects Strong Baseline v2.
- `complexity_score >= 2` selects the frozen Final Agent.
- The router reads only the user question. It never reads benchmark category, difficulty, expected result, or case ID.
- No router LLM is used and no answer fusion is performed.

Complexity features:

- Explicit multi-stage analysis.
- Multiple distinct business metrics.
- Nested ranking within groups.
- Derived metric or ratio combined with grouping.
- Three or more explicit business entities, including probable multi-hop relations.
- Three or more combined grouping/ranking/comparison/derived/stage operations.
- Explicit complex language structures such as grouped extrema or find-then-analyze requests.

Frozen paths:

- Fast path: Strong Baseline v2 commit `4cf4bc0`.
- Agentic path: Existing Final Agent commit `3d612df`.

The two frozen systems are not modified by this layer.

