from eval.strong_baseline import BUSINESS_CONTEXT, build_messages, extract_sql


def test_extract_sql():
    assert extract_sql("```sql\nSELECT 1;\n```") == "SELECT 1;"
    assert extract_sql("SELECT 1;") == "SELECT 1"


def test_context_has_basic_business_contracts():
    assert "orders.paid_amount" in BUSINESS_CONTEXT
    assert "order_items.quantity" in BUSINESS_CONTEXT
    assert "refund_status='approved'" in BUSINESS_CONTEXT
    assert "users.user_id = orders.user_id" in BUSINESS_CONTEXT


def test_retry_prompt_contains_execution_error():
    messages = build_messages("question", "schema", "SELECT nope", "Unknown column")
    assert "Unknown column" in messages[1]["content"]
    assert "SELECT nope" in messages[1]["content"]
