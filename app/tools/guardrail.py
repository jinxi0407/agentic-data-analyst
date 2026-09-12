"""Deterministic SQL guardrail for safe MySQL reads."""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import expressions as exp

from app.config import settings


FORBIDDEN = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "replace",
    "merge",
    "call",
    "set",
    "use",
}


@dataclass(frozen=True)
class GuardrailResult:
    ok: bool
    sql: str
    error: str = ""


def validate_and_rewrite_sql(sql: str) -> GuardrailResult:
    clean_sql = _strip_code_fences(sql).strip()
    clean_sql = clean_sql.rstrip(";").strip()
    if not clean_sql:
        return GuardrailResult(False, "", "SQL is empty.")

    statements = sqlglot.parse(clean_sql, read="mysql")
    if len(statements) != 1:
        return GuardrailResult(False, clean_sql, "Only one SQL statement is allowed.")

    lowered = re.sub(r"\s+", " ", clean_sql.lower())
    for keyword in FORBIDDEN:
        if re.search(rf"\b{keyword}\b", lowered):
            return GuardrailResult(False, clean_sql, f"Forbidden SQL keyword: {keyword.upper()}.")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        return GuardrailResult(False, clean_sql, "Only SELECT or WITH ... SELECT statements are allowed.")

    if statement.find(exp.Command):
        return GuardrailResult(False, clean_sql, "SQL commands are not allowed.")

    limited = _ensure_limit(statement)
    return GuardrailResult(True, limited.sql(dialect="mysql"), "")


def _strip_code_fences(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return text


def _ensure_limit(statement: exp.Select) -> exp.Select:
    existing = statement.args.get("limit")
    max_rows = settings.sql_max_rows
    if existing is None:
        return statement.limit(max_rows)

    try:
        current = int(existing.expression.name)
    except Exception:
        return statement.limit(max_rows)

    if current > max_rows:
        return statement.limit(max_rows)
    return statement
