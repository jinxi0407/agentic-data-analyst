import pytest
from pydantic import ValidationError

from app.agent.structured_intent import Intent, parse_intent


def payload():
    return dict(operation="rank", metric="sales_amount", dimensions=["user_id"],
                filters=[], time_range=None, direction="desc", limit=5,
                entities=["users", "orders"], target_grain="users", confidence=0.9)


def test_valid_intent():
    assert Intent.model_validate(payload()).limit == 5


@pytest.mark.parametrize("update", [{"entities": ["unknown"]}, {"limit": 0},
                                    {"confidence": 1.5}, {"extra": "ignored"}])
def test_invalid_intent(update):
    with pytest.raises(ValidationError):
        Intent.model_validate(payload() | update)


def test_fenced_json(monkeypatch):
    import json
    monkeypatch.setattr("app.agent.structured_intent.generate_text",
                        lambda *args, **kwargs: "```json\n" + json.dumps(payload()) + "\n```")
    assert parse_intent("customer spending", "schema")["entities"] == ["users", "orders"]
