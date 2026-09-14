"""Tests for PortReader — typed reader over PortRegistry.

Task 3 of the typed port graph redesign: PortReader resolves a PortRef
against the registry, optionally navigating into a field on the payload.

TDD RED: these tests must fail before the implementation lands.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lca.contracts.protocols.graph.errors import UnknownFieldError, UnsetPortError
from lca.contracts.protocols.graph.predicate import PortRef
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.port_registry import PortRegistry


class _RoutingPayload(BaseModel):
    action_type: str = "respond"
    should_terminate: bool = False
    confidence: float = 0.9


def test_read_port_returns_whole_value() -> None:
    """PortReader.read(ref) returns the full port value when ref.field is None."""
    reg = PortRegistry()
    payload = _RoutingPayload(action_type="use_tool")
    reg.set_typed_port("decision", payload, payload_type=_RoutingPayload)
    reader = PortReader(source_node="test_node", registry=reg)
    result = reader.read(PortRef(name="decision"))
    assert result is payload


def test_read_port_field_navigates_into_payload() -> None:
    """PortReader.read(ref) navigates into ref.field on the payload."""
    reg = PortRegistry()
    payload = _RoutingPayload(action_type="use_tool", should_terminate=True)
    reg.set_typed_port("decision", payload, payload_type=_RoutingPayload)
    reader = PortReader(source_node="test_node", registry=reg)
    assert reader.read(PortRef(name="decision", field="should_terminate")) is True
    assert reader.read(PortRef(name="decision", field="action_type")) == "use_tool"


def test_read_missing_port_raises_unset_port_error() -> None:
    """PortReader.read raises UnsetPortError when the port is not in the registry."""
    reg = PortRegistry()
    reader = PortReader(source_node="test_node", registry=reg)
    # "observation" is a valid PortName but was never written to the registry.
    with pytest.raises(UnsetPortError):
        reader.read(PortRef(name="observation"))


def test_read_unknown_field_raises_unknown_field_error() -> None:
    """PortReader.read raises UnknownFieldError when ref.field doesn't exist on payload_type."""
    reg = PortRegistry()
    payload = _RoutingPayload()
    reg.set_typed_port("decision", payload, payload_type=_RoutingPayload)
    reader = PortReader(source_node="test_node", registry=reg)
    with pytest.raises(UnknownFieldError):
        reader.read(PortRef(name="decision", field="nonexistent_field"))


def test_read_field_on_dict_payload_without_type() -> None:
    """When no payload_type is registered, field access on a dict payload uses dict key lookup."""
    reg = PortRegistry()
    reg.merge_output({"decision": {"action_type": "stop", "should_terminate": True}})
    reader = PortReader(source_node="test_node", registry=reg)
    # No payload_type registered → field access via dict key
    assert reader.read(PortRef(name="decision", field="action_type")) == "stop"


def test_read_field_on_untyped_non_dict_raises_unknown_field_error() -> None:
    """Field access on a non-dict value without payload_type raises UnknownFieldError."""
    reg = PortRegistry()
    reg.merge_output({"observation": 42})
    reader = PortReader(source_node="test_node", registry=reg)
    with pytest.raises(UnknownFieldError):
        reader.read(PortRef(name="observation", field="anything"))
