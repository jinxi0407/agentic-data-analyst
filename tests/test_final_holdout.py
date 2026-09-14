from collections import Counter

from eval.final_holdout import build_cases
from eval.run_final_holdout import is_infrastructure_error


def test_final_holdout_distribution():
    cases = build_cases()
    assert len(cases) == 250
    assert Counter(case["difficulty"] for case in cases) == {
        "easy": 125,
        "medium": 100,
        "hard": 25,
    }
    assert sum(case["paraphrase"] for case in cases) == 30


def test_infrastructure_error_classification():
    assert is_infrastructure_error("Qwen chat call failed: service unavailable")
    assert not is_infrastructure_error("Unknown column product_title")
    assert not is_infrastructure_error("ParseError: invalid expression")
