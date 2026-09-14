"""Tests for PortRegistry.read / port_type / set_typed_port extensions.

Task 3 of the typed port graph redesign: the registry gains typed read
and type-registration methods alongside the existing merge_output /
set_outer_input / build_input / snapshot / exit_subgraph surface.

TDD RED: these tests must fail before the implementation lands.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lca.contracts.protocols.graph.errors import UnsetPortError
from lca.framework.graph.port_registry import PortRegistry


class _DecisionPayload(BaseModel):
    action_type: str = "respond"
    should_terminate: bool = False


def test_read_returns_set_port_value() -> None:
    """read(name) returns the value stored via merge_output."""
    reg = PortRegistry()
    reg.merge_output({"decision": {"action_type": "use_tool"}})
    assert reg.read("decision") == {"action_type": "use_tool"}


def test_read_raises_unset_port_error_on_missing() -> None:
    """read(name) raises UnsetPortError when the port was never written."""
    reg = PortRegistry()
    with pytest.raises(UnsetPortError):
        reg.read("nonexistent_port")


def test_port_type_returns_registered_type() -> None:
    """port_type(name) returns the payload_type registered via set_typed_port."""
    reg = PortRegistry()
    payload = _DecisionPayload(action_type="stop")
    reg.set_typed_port("decision", payload, payload_type=_DecisionPayload)
    assert reg.port_type("decision") is _DecisionPayload


def test_port_type_returns_none_when_no_type_registered() -> None:
    """port_type(name) returns None for ports set via merge_output (no type info)."""
    reg = PortRegistry()
    reg.merge_output({"observation": "some_value"})
    assert reg.port_type("observation") is None


def test_set_typed_port_stores_value_and_type() -> None:
    """set_typed_port stores the value (readable via read) and registers the type."""
    reg = PortRegistry()
    payload = _DecisionPayload(action_type="think")
    reg.set_typed_port("decision", payload, payload_type=_DecisionPayload)
    assert reg.read("decision") is payload
    assert reg.port_type("decision") is _DecisionPayload


def test_set_typed_port_without_payload_type_stores_value_only() -> None:
    """set_typed_port with payload_type=None stores the value but no type."""
    reg = PortRegistry()
    reg.set_typed_port("raw_port", 42)
    assert reg.read("raw_port") == 42
    assert reg.port_type("raw_port") is None


def test_existing_merge_output_still_works() -> None:
    """Existing merge_output semantics are not broken by the new methods."""
    reg = PortRegistry()
    reg.merge_output({"a": 1, "b": 2})
    reg.merge_output({"b": 3})  # last-write-wins
    assert reg.read("a") == 1
    assert reg.read("b") == 3
    assert reg.snapshot() == {"a": 1, "b": 3}


def test_existing_set_outer_input_still_works() -> None:
    """Existing set_outer_input (setdefault) semantics are preserved."""
    reg = PortRegistry()
    reg.merge_output({"x": "inner_value"})
    reg.set_outer_input({"x": "outer_value", "y": "outer_y"})
    # outer input wins on first seed only; existing inner value kept
    assert reg.read("x") == "inner_value"
    assert reg.read("y") == "outer_y"
