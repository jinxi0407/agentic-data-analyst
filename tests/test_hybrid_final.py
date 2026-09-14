from eval.hybrid_final import AGENT_THRESHOLD, route_question, run_question


def test_router_defaults_straightforward_query_to_fast():
    decision = route_question("最近30天有效订单销售额是多少？")
    assert decision.route == "fast"
    assert decision.complexity_score < AGENT_THRESHOLD


def test_router_sends_nested_multimetric_query_to_agent():
    decision = route_question("每个品类中销售额最高的商品及其退款率是多少？")
    assert decision.route == "agent"
    assert decision.complexity_score >= AGENT_THRESHOLD
    assert "nested_group_ranking" in decision.reasons


def test_router_sends_multistage_multientity_query_to_agent():
    decision = route_question("先找出退款金额最高的商品，再比较这些商品对应客户的订单销售额。")
    assert decision.route == "agent"
    assert "multi_stage_analysis" in decision.reasons
    assert "multiple_business_entities" in decision.reasons


def test_hybrid_calls_only_fast_runner_for_fast_route():
    calls = []

    def fast(question):
        calls.append(("fast", question))
        return {"status": "success", "result": [{"value": 1}]}

    def agent(question):
        calls.append(("agent", question))
        raise AssertionError("agent path must not run")

    state = run_question("有效订单数是多少？", fast_runner=fast, agent_runner=agent)
    assert calls == [("fast", "有效订单数是多少？")]
    assert state["selected_route"] == "fast"


def test_hybrid_calls_only_agent_runner_for_complex_route():
    calls = []

    def fast(question):
        calls.append(("fast", question))
        raise AssertionError("fast path must not run")

    def agent(question):
        calls.append(("agent", question))
        return {"exec_status": "success", "query_result": [{"value": 1}]}

    question = "每个品类中销售额最高的商品及其退款率是多少？"
    state = run_question(question, fast_runner=fast, agent_runner=agent)
    assert calls == [("agent", question)]
    assert state["selected_route"] == "agent"
    assert state["complexity_score"] >= AGENT_THRESHOLD

