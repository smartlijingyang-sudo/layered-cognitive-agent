"""Test the extended contract surface for the typed port graph redesign.

Task 2 of the atomic cutover: validates that PortSpec.payload_type is
load-bearing (accepts a Pydantic model class, not just a string) and
that NodeIOSchema carries a terminal_predicate for plan-level termination.

These tests exercise real Pydantic validation — no mocks.
"""
from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.graph.node_io import NodeIOSchema, NodeOutput, PortSpec
from lca.contracts.protocols.graph.predicate import PortRef, Predicate


class _FakePayload(BaseModel):
    action_type: str = ""
    should_terminate: bool = False


def test_port_spec_payload_type_load_bearing() -> None:
    """PortSpec.payload_type accepts a BaseModel subclass (not just a string).

    The type is stored as-is for lift-time field validation (Task 5).
    """
    spec = PortSpec(name="decision", payload_type=_FakePayload)
    assert spec.payload_type is _FakePayload


def test_node_io_schema_terminal_predicate_field() -> None:
    """NodeIOSchema carries an optional terminal_predicate Predicate."""
    pred = Predicate(
        kind="eq",
        port=PortRef(name="decision", field="should_terminate"),
        value=True,
    )
    schema = NodeIOSchema(inputs=(), outputs=(), terminal_predicate=pred)
    assert schema.terminal_predicate == pred
    assert schema.terminal_predicate is not None
    assert schema.terminal_predicate.port is not None
    assert schema.terminal_predicate.port.name == "decision"


def test_node_io_schema_terminal_predicate_defaults_none() -> None:
    """terminal_predicate is optional; defaults to None (no termination)."""
    schema = NodeIOSchema(inputs=(), outputs=())
    assert schema.terminal_predicate is None


def test_node_output_has_no_ad_hoc_fields() -> None:
    """NodeOutput dropped result_kind/next_hint/next_hints.

    Only port_values + producer_node remain; routing goes through
    the typed RoutingDecision port (Task 8 / D4).
    """
    out = NodeOutput(port_values={"decision": {"action_type": "respond"}}, producer_node="n1")
    assert out.port_values == {"decision": {"action_type": "respond"}}
    assert out.producer_node == "n1"
    # The three ad-hoc fields are gone:
    assert "result_kind" not in NodeOutput.model_fields
    assert "next_hint" not in NodeOutput.model_fields
    assert "next_hints" not in NodeOutput.model_fields


def test_node_output_rejects_ad_hoc_fields() -> None:
    """Passing removed fields raises ValidationError (extra='forbid')."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NodeOutput(port_values={}, result_kind="decision")
    with pytest.raises(ValidationError):
        NodeOutput(port_values={}, next_hint="stop")
    with pytest.raises(ValidationError):
        NodeOutput(port_values={}, next_hints={"x": 1})


def test_port_spec_payload_type_none_means_dynamic() -> None:
    """payload_type=None is valid — dynamic port, no field access in predicates."""
    spec = PortSpec(name="observation")
    assert spec.payload_type is None
    spec2 = PortSpec(name="manifest", payload_type=None)
    assert spec2.payload_type is None
