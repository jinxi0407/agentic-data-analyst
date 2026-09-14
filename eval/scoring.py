"""Frozen result comparison and database fingerprint helpers."""

from __future__ import annotations

import hashlib
import json
import math
from itertools import permutations


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def fingerprint(fetch):
    tables = [
        ("users", "user_id"),
        ("products", "product_id"),
        ("orders", "order_id"),
        ("order_items", "order_item_id"),
        ("refunds", "refund_id"),
        ("core_table", "id"),
        ("core_field", "id"),
    ]
    return {
        table: digest(fetch(f"SELECT * FROM {table} ORDER BY {key}"))
        for table, key in tables
    }


def same_value(expected, actual):
    if expected is None or actual is None:
        return expected is actual
    if isinstance(expected, (int, float)):
        try:
            return math.isclose(
                float(expected), float(actual), rel_tol=0, abs_tol=0.005
            )
        except (ValueError, TypeError):
            return False
    return str(expected) == str(actual)


def compare(expected, actual, ordered=False):
    if len(expected) != len(actual):
        return False
    if not expected:
        return True
    width = len(expected[0])
    if any(len(row) != width for row in actual):
        return False
    expected_values = [list(row.values()) for row in expected]
    actual_values = [list(row.values()) for row in actual]
    for permutation in permutations(range(width)):
        remaining = list(actual_values)
        valid = True
        for row in expected_values:
            choices = range(min(1, len(remaining))) if ordered else range(len(remaining))
            match = next(
                (
                    index
                    for index in choices
                    if all(
                        same_value(value, remaining[index][column])
                        for value, column in zip(row, permutation)
                    )
                ),
                None,
            )
            if match is None:
                valid = False
                break
            remaining.pop(match)
        if valid:
            return True
    return False

