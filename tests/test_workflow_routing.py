from app.agent.workflow import route_after_execute, route_after_external_node, route_after_guardrail


def test_retry_after_validation_error():
    assert route_after_guardrail({"validation_error": "bad", "retry_count": 0}) == "repair_sql"


def test_stop_after_max_retry():
    assert route_after_execute({"execution_error": "bad", "retry_count": 2}) == "final_error"


def test_external_error_goes_to_final_error():
    assert route_after_external_node({"execution_error": "missing key", "status": "error"}) == "final_error"
