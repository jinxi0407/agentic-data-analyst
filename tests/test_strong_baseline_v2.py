from eval.strong_baseline_v2 import (
    FEW_SHOT_EXAMPLES,
    STATIC_SCHEMA_METADATA,
    build_messages,
    normalize_aliases,
)


def test_alias_normalization_is_fixed_vocabulary_only():
    question = "客户成交额、产品销售数量和退款额"
    assert normalize_aliases(question) == "用户销售额、商品销量和退款金额"


def test_static_metadata_has_enums_and_field_meanings():
    assert "paid/completed/shipped/cancelled/unpaid" in STATIC_SCHEMA_METADATA
    assert "approved/rejected/pending" in STATIC_SCHEMA_METADATA
    assert "paid_amount is actual customer payment" in STATIC_SCHEMA_METADATA


def test_exactly_five_generic_examples():
    assert FEW_SHOT_EXAMPLES.count("Question:") == 5
    assert FEW_SHOT_EXAMPLES.count("SQL:") == 5


def test_prompt_has_original_and_normalized_question():
    messages = build_messages("客户成交额", "schema")
    assert "Original question:\n客户成交额" in messages[1]["content"]
    assert "Question with vocabulary aliases normalized:\n用户销售额" in messages[1]["content"]
