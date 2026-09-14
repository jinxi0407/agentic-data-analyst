from collections import Counter

from eval.final_holdout_v2 import build_cases
from eval.run_final_holdout_v2 import is_infrastructure_error


def test_holdout_v2_distribution_and_unique_questions():
    cases = build_cases()
    assert len(cases) == 250
    assert len({case["question"] for case in cases}) == 250
    assert Counter(case["difficulty"] for case in cases) == {
        "easy": 125, "medium": 100, "hard": 25,
    }
    assert sum(case["paraphrase"] for case in cases) == 30


def test_only_true_infrastructure_errors_are_rerunnable():
    assert is_infrastructure_error("Timeout while calling DashScope")
    assert is_infrastructure_error("MySQL connection refused")
    assert not is_infrastructure_error("ParseError: invalid expression")
    assert not is_infrastructure_error("Unknown column in field list")
