"""Tests for PR-2 close-out registry and adapter."""
from __future__ import annotations

import pytest

from lca.cognition.wire.close_out_registry import (
    CLOSE_OUT_REGISTRY,
    CloseOutField,
    close_out_projection,
    field_names,
)
from lca.cognition.wire.close_out_adapter import CloseOutAdapter


class _StubOutput:
    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestRegistry:
    def test_contains_five_canonical_fields(self) -> None:
        names = {f.name for f in CLOSE_OUT_REGISTRY}
        assert names == {"decision", "receipt", "observation", "reflection", "response"}

    def test_priorities_distinct(self) -> None:
        priorities = [f.priority for f in CLOSE_OUT_REGISTRY]
        assert len(priorities) == len(set(priorities)), "duplicate priority values"

    def test_decision_has_highest_priority(self) -> None:
        top = max(CLOSE_OUT_REGISTRY, key=lambda f: f.priority)
        assert top.name == "decision"

    def test_field_names_in_priority_order(self) -> None:
        names = field_names()
        assert names[0] == "decision"
        assert len(names) == 5

    def test_payload_types_are_classes(self) -> None:
        for f in CLOSE_OUT_REGISTRY:
            assert isinstance(f.payload_type, type), f.name


class TestProjection:
    def test_first_non_none_wins(self) -> None:
        outputs = {
            "a": _StubOutput(observation="o1"),
            "b": _StubOutput(observation="o2"),
        }
        result = close_out_projection(outputs)
        assert result == {"observation": "o1"}

    def test_priority_overrides_iteration_order(self) -> None:
        outputs = {
            "low": _StubOutput(observation="o_observation"),
            "high": _StubOutput(decision="d_decision"),
        }
        result = close_out_projection(outputs)
        assert "observation" in result
        assert "decision" in result
        # Both fields exist; neither overwrites the other.
        assert result["observation"] == "o_observation"
        assert result["decision"] == "d_decision"

    def test_missing_attribute_is_skipped(self) -> None:
        outputs = {"a": _StubOutput(unrelated="x")}
        result = close_out_projection(outputs)
        assert result == {}

    def test_none_value_is_skipped(self) -> None:
        outputs = {"a": _StubOutput(observation=None)}
        result = close_out_projection(outputs)
        assert result == {}

    def test_pure_function(self) -> None:
        outputs = {"a": _StubOutput(decision="d")}
        r1 = close_out_projection(outputs)
        r2 = close_out_projection(outputs)
        assert r1 == r2


class TestAdapter:
    def test_default_uses_registry(self) -> None:
        adapter = CloseOutAdapter()
        assert adapter.field_names() == field_names()

    def test_custom_fields(self) -> None:
        custom = (CloseOutField(name="decision", payload_type=object, priority=10),)
        adapter = CloseOutAdapter(fields=custom)
        assert adapter.field_names() == ("decision",)
        assert "observation" not in adapter.field_names()

    def test_custom_project_skips_unknown_field(self) -> None:
        custom = (CloseOutField(name="observation", payload_type=object, priority=10),)
        adapter = CloseOutAdapter(fields=custom)
        outputs = {"a": _StubOutput(decision="d")}
        # decision is not in custom fields, so the adapter ignores it.
        assert adapter.project(outputs) == {}

    def test_payload_types(self) -> None:
        adapter = CloseOutAdapter()
        types = adapter.payload_types()
        assert "decision" in types
        assert "response" in types