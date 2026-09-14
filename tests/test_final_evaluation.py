import json
from collections import Counter
from pathlib import Path

from eval.run_final_evaluation import is_infrastructure_error
from eval.scoring import digest


def test_frozen_final_release_manifest():
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / "eval/final_release_holdout_300.json").read_text())
    manifest = json.loads((root / "eval/final_release_manifest.json").read_text())
    assert len(cases) == 300
    assert digest(cases) == manifest["cases_sha256"]
    assert Counter(case["difficulty"] for case in cases) == {
        "easy": 150, "medium": 120, "hard": 30,
    }


def test_only_transient_infrastructure_failures_are_rerunnable():
    assert is_infrastructure_error("API timed out while reading response")
    assert is_infrastructure_error("Lost connection to MySQL server during query")
    assert not is_infrastructure_error("ParseError: invalid expression")
    assert not is_infrastructure_error("LLM malformed output")

