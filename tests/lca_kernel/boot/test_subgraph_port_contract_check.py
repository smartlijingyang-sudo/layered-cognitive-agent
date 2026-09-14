"""Tests for :class:`SubgraphPortContractCheck`.

Five cases cover the decision tree:

- subgraph delegate with empty ``inner_io_schema`` → reject
- subgraph delegate with inputs-only ``inner_io_schema`` → pass
- subgraph delegate with outputs-only ``inner_io_schema`` → pass
- leaf node (no ``subgraph_ref``) → pass (not a delegate)
- plan with no subgraph delegates at all → pass
"""

from __future__ import annotations

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanNode, SubgraphReference
from lca_kernel.boot.plan_validation.checks.subgraph_port_contract import (
    SubgraphPortContractCheck,
)


def _subgraph_ref() -> SubgraphReference:
    return SubgraphReference(
        plan_ref="inner.plan",
        entry_node="inner.entry",
        binding_edge="outer.edge",
    )


def _leaf_node(node_id: str, *, entry: bool = False, terminal: bool = False) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        entry=entry,
        terminal=terminal,
    )


def _subgraph_node(
    node_id: str,
    inner_schema: NodeIOSchema | None,
    *,
    entry: bool = False,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.SUBGRAPH,
        subgraph_ref=_subgraph_ref(),
        inner_io_schema=inner_schema,
        entry=entry,
    )


def _plan(*nodes: PlanNode) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes))


class TestSubgraphPortContractCheck:
    def setup_method(self) -> None:
        self.check = SubgraphPortContractCheck()

    def test_empty_inner_schema_raises(self) -> None:
        plan = _plan(
            _subgraph_node("sg", NodeIOSchema(), entry=True),
            _leaf_node("downstream", terminal=True),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert err is not None
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.node_id == "sg"
        assert "empty inner_io_schema" in str(err)

    def test_inputs_only_does_not_raise(self) -> None:
        schema = NodeIOSchema(inputs=(PortSpec(name="decision"),))
        plan = _plan(
            _subgraph_node("sg", schema, entry=True),
            _leaf_node("downstream", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    def test_outputs_only_does_not_raise(self) -> None:
        schema = NodeIOSchema(outputs=(PortSpec(name="act_outcome"),))
        plan = _plan(
            _subgraph_node("sg", schema, entry=True),
            _leaf_node("downstream", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    def test_leaf_node_does_not_raise(self) -> None:
        # Leaf node with no subgraph_ref is never inspected.
        plan = _plan(
            _leaf_node("leaf", entry=True, terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    def test_plan_without_subgraph_delegates_does_not_raise(self) -> None:
        plan = _plan(
            _leaf_node("a", entry=True),
            _leaf_node("b", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "subgraph_port_contract"
        assert self.check.label
