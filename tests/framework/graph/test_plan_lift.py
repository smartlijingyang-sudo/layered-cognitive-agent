"""Lift-time predicate and termination validation (Task 5).

Validates that:
- Every edge Predicate references ports declared by the source node's outputs.
- Every Predicate.field exists on the port's payload_type.
- Every plan has a termination policy (terminal node or terminal_predicate).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.framework.graph.lifter import (
    _validate_termination,
    lift_graph_spec,
    validate_predicates,
)


class DecisionPayload(BaseModel):
    action_type: str
    response: str = ""


def _plan_with_predicate(
    outputs: tuple[PortSpec, ...],
    pred: Predicate,
) -> Plan:
    """Build a Plan directly with typed outputs for validation testing."""
    node_a = PlanNode(
        id="a",
        binding="node_executor",
        io_schema=NodeIOSchema(outputs=outputs),
        entry=True,
    )
    node_b = PlanNode(id="b", binding="node_executor", terminal=True)
    edge_ab = PlanEdge(source="a", target="b", when=pred)
    return Plan(id="test", nodes=(node_a, node_b), edges=(edge_ab,))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestLiftValidation:
    def test_lift_happy_path(self) -> None:
        """Valid spec with Predicate referencing declared output lifts clean."""
        spec = {
            "id": "happy",
            "nodes": [
                {
                    "id": "think",
                    "binding": "node_executor",
                    "outputs": ["decision"],
                    "entry": True,
                },
                {
                    "id": "act",
                    "binding": "node_executor",
                    "inputs": ["decision"],
                    "terminal": True,
                },
            ],
            "edges": [
                {
                    "from": "think",
                    "to": "act",
                    "when": Predicate(
                        kind="eq",
                        port=PortRef(name="decision"),
                        value="use_tool",
                    ),
                },
            ],
        }
        plan = lift_graph_spec(spec)
        assert plan.id == "happy"
        assert len(plan.edges) == 1

    # ---------------------------------------------------------------------------
    # Port-not-declared
    # ---------------------------------------------------------------------------

    def test_lift_raises_when_predicate_port_not_declared(self) -> None:
        """Edge Predicate references a port the source node doesn't declare."""
        pred = Predicate(
            kind="eq",
            port=PortRef(name="nonexistent_port"),
            value="x",
        )
        plan = _plan_with_predicate(
            outputs=(PortSpec(name="decision"),),
            pred=pred,
        )
        with pytest.raises(PlanLiftError) as exc_info:
            validate_predicates(plan)
        err = exc_info.value
        assert err.port_name == "nonexistent_port"
        assert err.plan_id == "test"

    # ---------------------------------------------------------------------------
    # Field-not-on-payload-type
    # ---------------------------------------------------------------------------

    def test_lift_raises_when_predicate_field_not_on_payload_type(self) -> None:
        """Predicate.field references a field that doesn't exist on payload_type."""
        pred = Predicate(
            kind="eq",
            port=PortRef(name="decision", field="bogus_field"),
            value="use_tool",
        )
        plan = _plan_with_predicate(
            outputs=(PortSpec(name="decision", payload_type=DecisionPayload),),
            pred=pred,
        )
        with pytest.raises(PlanLiftError) as exc_info:
            validate_predicates(plan)
        err = exc_info.value
        assert err.port_name == "decision"
        assert err.plan_id == "test"

    # ---------------------------------------------------------------------------
    # No termination policy
    # ---------------------------------------------------------------------------

    def test_lift_raises_when_plan_has_no_termination(self) -> None:
        """Plan with no terminal node and no terminal_predicate is rejected."""
        node_a = PlanNode(
            id="a",
            binding="node_executor",
            io_schema=NodeIOSchema(),
        )
        node_b = PlanNode(
            id="b",
            binding="node_executor",
            io_schema=NodeIOSchema(),
        )
        plan = Plan.model_construct(
            id="no_term",
            nodes=(node_a, node_b),
            edges=(),
            approval_resume_node=None,
            declared_inputs=(),
        )
        with pytest.raises(PlanLiftError) as exc_info:
            _validate_termination(plan)
        assert "termination" in str(exc_info.value).lower()


class TestPortSpecProjection:
    """`_to_port_specs` must keep every declared port instead of dropping any."""

    def test_every_string_port_survives_lift(self) -> None:
        from lca.framework.graph.lifter import _to_port_specs

        names = ["decision", "observation", "a b", "x" * 200, "routing.next"]
        specs = _to_port_specs(names)
        assert [s.name for s in specs] == names

    def test_single_string_is_treated_as_one_port(self) -> None:
        from lca.framework.graph.lifter import _to_port_specs

        assert [s.name for s in _to_port_specs("decision")] == ["decision"]

    def test_non_string_and_empty_entries_are_filtered(self) -> None:
        from lca.framework.graph.lifter import _to_port_specs

        assert [s.name for s in _to_port_specs(["ok", "", None, 7])] == ["ok"]
        assert _to_port_specs(None) == ()
        assert _to_port_specs({"a": 1}) == ()
