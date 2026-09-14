"""Tests for PortName as a string alias (not a business-name Literal).

Verifies the design-level fix: the graph framework accepts any port name
and does not hardcode business knowledge. Validation happens at the IO
schema level (dedup) and at lift time (port existence), not at the type level.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanNode
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.predicate import PortRef


class TestPortNameAcceptsAnyString:
    """PortName is a NewType alias for str; Pydantic accepts any string."""

    def test_port_spec_accepts_arbitrary_name(self) -> None:
        spec = PortSpec(name="anything_here")
        assert spec.name == "anything_here"

    def test_port_spec_accepts_business_name(self) -> None:
        spec = PortSpec(name="decision")
        assert spec.name == "decision"

    def test_port_spec_accepts_dotted_name(self) -> None:
        spec = PortSpec(name="custom.nested.port")
        assert spec.name == "custom.nested.port"

    def test_port_ref_accepts_arbitrary_name(self) -> None:
        ref = PortRef(name="x.y.z")
        assert ref.name == "x.y.z"

    def test_port_ref_accepts_business_name(self) -> None:
        ref = PortRef(name="observation")
        assert ref.name == "observation"

    def test_plan_declared_inputs_accepts_any_port_name(self) -> None:
        p = Plan(
            id="test",
            nodes=(PlanNode(id="n1", binding="node_executor", entry=True),),
            declared_inputs=(PortName("custom_a"), PortName("custom_b")),
        )
        assert p.declared_inputs == ("custom_a", "custom_b")


class TestDedupInvariantHolds:
    """NodeIOSchema still rejects duplicate port names across inputs+outputs."""

    def test_duplicate_in_inputs_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate port name"):
            NodeIOSchema(
                inputs=(PortSpec(name="dup"), PortSpec(name="dup")),
            )

    def test_duplicate_in_outputs_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate port name"):
            NodeIOSchema(
                outputs=(PortSpec(name="dup"), PortSpec(name="dup")),
            )

    def test_duplicate_across_inputs_outputs_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate port name"):
            NodeIOSchema(
                inputs=(PortSpec(name="dup"),),
                outputs=(PortSpec(name="dup"),),
            )

    def test_distinct_names_accepted(self) -> None:
        schema = NodeIOSchema(
            inputs=(PortSpec(name="a"), PortSpec(name="b")),
            outputs=(PortSpec(name="c"),),
        )
        assert schema.required_inputs() == ("a", "b")
        assert schema.output_names() == frozenset({"c"})


class TestPydanticConfigPreserved:
    """frozen=True and extra='forbid' still enforced on all models."""

    def test_port_spec_frozen(self) -> None:
        spec = PortSpec(name="x")
        with pytest.raises(ValidationError):
            spec.name = "y"  # type: ignore[misc]

    def test_port_spec_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PortSpec(name="x", unknown_field="bad")  # type: ignore[call-arg]

    def test_port_ref_frozen(self) -> None:
        ref = PortRef(name="x")
        with pytest.raises(ValidationError):
            ref.name = "y"  # type: ignore[misc]

    def test_port_ref_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PortRef(name="x", extra="bad")  # type: ignore[call-arg]
