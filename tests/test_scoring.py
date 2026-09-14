from eval.scoring import compare


def test_strict_numeric_scoring():
    assert not compare([{"a": 100}], [{"a": 102}])
    assert compare([{"a": 1.23}], [{"x": 1.234}])
    assert not compare([{"a": None}], [{"a": 0}])


def test_order_and_multiplicity():
    expected = [{"name": "A", "value": 10}, {"name": "B", "value": 20}]
    assert compare(expected, list(reversed(expected)))
    assert not compare(expected, list(reversed(expected)), ordered=True)
    assert not compare(expected, [expected[0], expected[0]])
    assert not compare([{"a": 1}], [{"a": 1, "extra": 2}])

