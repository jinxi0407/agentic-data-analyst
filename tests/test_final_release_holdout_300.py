from collections import Counter

from eval.final_release_holdout_300 import build_cases
from eval.run_final_release_holdout_300 import is_infrastructure_error


def test_final_release_holdout_distribution():
    cases = build_cases()
    assert len(cases) == 300
    assert len({case["question"] for case in cases}) == 300
    assert Counter(case["difficulty"] for case in cases) == {
        "easy": 150, "medium": 120, "hard": 30,
    }
    assert Counter(case["category"] for case in cases) == {
        "filtering_aggregation": 90,
        "top_k_ranking": 60,
        "time_trend": 60,
        "one_two_table_join": 45,
        "refund_customer_product": 30,
        "complex": 15,
    }
    assert sum(case["paraphrase"] for case in cases) == 36


def test_only_transient_infrastructure_failures_are_rerunnable():
    assert is_infrastructure_error("API timed out while reading response")
    assert is_infrastructure_error("Lost connection to MySQL server during query")
    assert not is_infrastructure_error("ParseError: invalid expression")
    assert not is_infrastructure_error("LLM malformed output")
    assert not is_infrastructure_error("Unknown column in field list")
