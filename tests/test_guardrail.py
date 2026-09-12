from app.tools.guardrail import validate_and_rewrite_sql


def test_select_is_allowed_and_limited():
    result = validate_and_rewrite_sql("SELECT * FROM orders")
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_delete_is_blocked():
    result = validate_and_rewrite_sql("DELETE FROM orders")
    assert not result.ok
    assert "Forbidden" in result.error


def test_multi_statement_is_blocked():
    result = validate_and_rewrite_sql("SELECT * FROM orders; SELECT * FROM users")
    assert not result.ok
