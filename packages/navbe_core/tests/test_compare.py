"""Unit tests for structured JSON compare (_diff)."""

from navbe_core.steps import _diff


def test_identical_dicts() -> None:
    assert _diff({"a": 1}, {"a": 1}, "$") == []


def test_missing_key() -> None:
    diffs = _diff({"a": 1, "b": 2}, {"a": 1}, "$")
    assert any(d["path"] == "$.b" for d in diffs)


def test_nested_diff() -> None:
    diffs = _diff({"x": {"y": 1}}, {"x": {"y": 2}}, "$")
    assert diffs[0]["path"] == "$.x.y"
    assert diffs[0]["expected"] == 1
    assert diffs[0]["actual"] == 2


def test_list_length_diff() -> None:
    diffs = _diff([1, 2], [1, 2, 3], "$")
    assert any("length" in d["path"] for d in diffs)
