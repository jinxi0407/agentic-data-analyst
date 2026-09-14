from eval.run_clarification import report


def test_decision_independent_of_sql_failure():
    case = {"id": "1", "should_clarify": False}
    row = {"id": "1", "first_status": "failed", "triggered": False,
           "interactive_correct": False, "first_latency_s": 1, "total_latency_s": 1}
    result = report([case], [row])
    assert result["decision_accuracy"] == 100
    assert result["overall_interactive_success_rate"] == 0


def test_format_failure_not_a_true_negative():
    case = {"id": "1", "should_clarify": False}
    row = {"id": "1", "first_status": "clarification_unavailable", "triggered": False,
           "interactive_correct": False, "first_latency_s": 1, "total_latency_s": 1}
    assert report([case], [row])["decision_accuracy"] == 0
