"""Pin the ``otel_safe_attributes`` contract (regression guard).

``e51902b07`` (RET505 hygiene) dropped the ``else:`` in front of the
``json.dumps`` fallback, so every primitive attribute (str/int/float/bool)
is now JSON-encoded a second time (``"ValueError"`` -> ``'"ValueError"'``).
These unit tests pin the intended contract: primitives pass through
unchanged, ``None`` is dropped, everything else becomes a JSON string.
"""

from __future__ import annotations

import json
from enum import Enum

import pytest

from lca.infrastructure.observability.adapters.policy import otel_safe_attributes


class _Color(Enum):
    RED = "red"


def test_primitives_pass_through_unchanged() -> None:
    attrs = {
        "s": "ValueError",
        "i": 5,
        "f": 1.5,
        "b": True,
    }
    out = otel_safe_attributes(attrs)
    assert out == attrs


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ValueError", "ValueError"),
        (5, 5),
        (1.5, 1.5),
        (False, False),
    ],
)
def test_primitive_identity_per_type(value: object, expected: object) -> None:
    assert otel_safe_attributes({"k": value}) == {"k": expected}


def test_none_is_dropped() -> None:
    assert otel_safe_attributes({"k": None, "ok": 1}) == {"ok": 1}


def test_nested_values_become_json_strings() -> None:
    out = otel_safe_attributes({"d": {"a": 1}, "l": [1, 2]})
    assert out["d"] == json.dumps({"a": 1}, ensure_ascii=False)
    assert out["l"] == json.dumps([1, 2], ensure_ascii=False)


def test_enum_becomes_its_value_string() -> None:
    out = otel_safe_attributes({"c": _Color.RED})
    assert out["c"] == json.dumps("red", ensure_ascii=False)


def test_empty_input_empty_output() -> None:
    assert otel_safe_attributes({}) == {}
