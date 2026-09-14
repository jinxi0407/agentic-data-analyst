"""Interactive entrypoint; run_question remains the frozen v1.0 direct engine."""

import time
from datetime import date

from eval.strong_baseline_v2 import run_question
from app.agent.clarification import ClarificationContext, GateUnavailable, decide


def run_interactive(question, clarification_answer=None, clarification_context=None,
                    reference_date=None):
    started = time.perf_counter()
    context = clarification_context
    reference = context.reference_date if context else (reference_date or date.today())
    original = context.original_question if context else question
    base = {"question": original, "engine": "Production NL2SQL Engine",
            "sql": "", "result": [], "retry_count": 0, "trace": [],
            "needs_clarification": False}
    try:
        decision = decide(original, reference_date=reference, context=context,
                          answer=clarification_answer)
    except GateUnavailable as exc:
        return base | {"status": "clarification_unavailable", "error": str(exc),
                       "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    base["trace"] = [{"stage": "clarification", "status": decision.decision,
                       "ambiguity_type": decision.ambiguity_type, "reason": decision.reason}]
    if decision.decision == "clarify":
        if context:
            base.update(status="needs_rephrase", error="信息仍不足，请重新提交一个明确的完整问题。")
        else:
            pending = ClarificationContext(original_question=original,
                ambiguity_type=decision.ambiguity_type,
                clarification_question=decision.clarification_question, reference_date=reference)
            base.update(status="needs_clarification", needs_clarification=True,
                        clarification_question=decision.clarification_question,
                        clarification_context=pending.model_dump(mode="json"))
    else:
        # Preserve the original constraints rather than trusting a model paraphrase alone.
        merged = f"参考日期：{reference.isoformat()}（问题内显式参考日期优先）。\n原始问题：{original}"
        if context:
            merged += (f"\n澄清问题：{context.clarification_question}"
                       f"\n用户澄清回答：{clarification_answer}")
        result = run_question(merged)
        base.update(result)
        base["question"] = original
        base["resolved_question"] = merged
        base["trace"] = [{"stage": "clarification", "status": "proceed"}] + result.get("trace", [])
    base["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return base

__all__ = ["run_question", "run_interactive"]
