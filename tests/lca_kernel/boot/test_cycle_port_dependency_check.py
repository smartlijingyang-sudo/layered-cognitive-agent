"""Tests for :class:`CyclePortDependencyCheck`.

Six cases cover the decision tree:

- Mutual port dependency inside a 2-node SCC → reject (deadlock)
- One-way port dependency inside a 2-node SCC → pass
- One-way port dependency across a 3-node SCC → pass (linear within cycle)
- Linear 3-node plan with no SCC → pass
- ``terminal_predicate`` node participating in a mutual port cycle → reject
- Subgraph delegate node in cycle → skip the subgraph pair → pass

The check is purely about *mutual* port requirements inside a
strongly connected component — single-direction cycles are fine
because the runtime can still schedule them via ``max_visits`` or
``terminal_predicate``.
"""
from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode, SubgraphReference
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca_kernel.boot.plan_validation.checks.cycle_port_dependency import (
    CyclePortDependencyCheck,
)


def _subgraph_ref() -> SubgraphReference:
    return SubgraphReference(
        plan_ref="inner.plan",
        entry_node="inner.entry",
        binding_edge="outer.edge",
    )


def _node(
    node_id: str,
    *,
    entry: bool = False,
    terminal: bool = False,
    io_schema: NodeIOSchema | None = None,
    subgraph_ref: SubgraphReference | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.SUBGRAPH if subgraph_ref is not None else BindingKind.NODE_EXECUTOR,
        config={},
        terminal=terminal,
        entry=entry,
        subgraph_ref=subgraph_ref,
        io_schema=io_schema if io_schema is not None else NodeIOSchema(),
    )


def _plan(*nodes: PlanNode, edges: tuple[PlanEdge, ...] = ()) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes), edges=edges)


class TestCyclePortDependencyCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = CyclePortDependencyCheck()

    # ------------------------------------------------------------------
    # Case 1: 2-node SCC with mutual port dependency → reject
    # ------------------------------------------------------------------

    def test_two_node_mutual_port_dependency_raises(self) -> None:
        """a needs 'x' from b, b needs 'y' from a → deadlock."""
        a_io = NodeIOSchema(
            inputs=(PortSpec(name="y"),),
            outputs=(PortSpec(name="x"),),
        )
        b_io = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
            outputs=(PortSpec(name="y"),),
        )
        plan = _plan(
            _node("a", entry=True, io_schema=a_io),
            _node("b", io_schema=b_io),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "b" in msg
        assert "x" in msg
        assert "y" in msg
        assert "deadlock" in msg

    # ------------------------------------------------------------------
    # Case 2: 2-node SCC with one-way port dependency → pass
    # ------------------------------------------------------------------

    def test_two_node_one_way_port_dependency_does_not_raise(self) -> None:
        """a produces 'x', b consumes 'x'; a needs nothing from b. Schedulable."""
        a_io = NodeIOSchema(
            outputs=(PortSpec(name="x"),),
        )
        b_io = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
        )
        plan = _plan(
            _node("a", entry=True, io_schema=a_io),
            _node("b", io_schema=b_io),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 3: 3-node SCC with linear port chain a→b→c → pass
    # ------------------------------------------------------------------

    def test_three_node_scc_linear_port_chain_does_not_raise(self) -> None:
        """a→b→c→a with linear port dependencies — not mutual, schedulable."""
        a_io = NodeIOSchema(
            inputs=(PortSpec(name="z"),),
            outputs=(PortSpec(name="x"),),
        )
        b_io = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
            outputs=(PortSpec(name="y"),),
        )
        c_io = NodeIOSchema(
            inputs=(PortSpec(name="y"),),
            outputs=(PortSpec(name="z"),),
        )
        plan = _plan(
            _node("a", entry=True, io_schema=a_io),
            _node("b", io_schema=b_io),
            _node("c", io_schema=c_io),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="c"),
                PlanEdge(source="c", target="a"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 4: Linear 3-node plan with no SCC → pass
    # ------------------------------------------------------------------

    def test_linear_plan_does_not_raise(self) -> None:
        """a→b→c, no cycles at all — no SCC of size >= 2, trivially passes."""
        a_io = NodeIOSchema(outputs=(PortSpec(name="x"),))
        b_io = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
            outputs=(PortSpec(name="y"),),
        )
        c_io = NodeIOSchema(inputs=(PortSpec(name="y"),))
        plan = _plan(
            _node("a", entry=True, io_schema=a_io),
            _node("b", io_schema=b_io),
            _node("c", terminal=True, io_schema=c_io),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="c"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 5: terminal_predicate node in mutual port cycle → reject
    # ------------------------------------------------------------------

    def test_terminal_predicate_in_cycle_still_rejects_mutual_dependency(self) -> None:
        """Predicate-equipped node still participates in mutual dependency check."""
        a_io = NodeIOSchema(
            inputs=(PortSpec(name="y"),),
            outputs=(PortSpec(name="x"),),
        )
        pred = Predicate(kind="exists", port=PortRef(name="done"))
        b_io = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
            outputs=(PortSpec(name="y"),),
            terminal_predicate=pred,
        )
        plan = _plan(
            _node("a", entry=True, io_schema=a_io),
            _node("b", io_schema=b_io),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "deadlock" in msg
        assert "a" in msg
        assert "b" in msg

    # ------------------------------------------------------------------
    # Case 6: Subgraph delegate node in cycle → skip subgraph pair → pass
    # ------------------------------------------------------------------

    def test_subgraph_delegate_in_cycle_is_skipped(self) -> None:
        """Subgraph delegate port resolution is opaque to outer kernel — skip."""
        # a is a leaf with no ports; b is a subgraph delegate with ports.
        # Even if both were tight together in an SCC, the check must
        # skip because subgraph resolution is delegated to the inner plan.
        a_io = NodeIOSchema()
        b_inner = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
            outputs=(PortSpec(name="y"),),
        )
        b_io = NodeIOSchema(
            inputs=(PortSpec(name="x"),),
            outputs=(PortSpec(name="y"),),
        )
        plan = _plan(
            _node("a", entry=True, io_schema=a_io),
            _node(
                "b",
                io_schema=b_io,
                subgraph_ref=_subgraph_ref(),
                # subgraph_ref is the opaque flag — skip port check
            ),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        # The presence of subgraph_ref on b means b is skipped from
        # pair inspection; a has no required_inputs so no mutual
        # dependency with anyone; plan passes.
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Sanity: empty plan
    # ------------------------------------------------------------------

    def test_empty_plan_does_not_raise(self) -> None:
        plan = Plan(id="empty.plan", nodes=(), edges=())
        assert self.check.run(plan, plan_id="empty.plan") is None

    # ------------------------------------------------------------------
    # Sanity: check_id / label
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "cycle_port_dependency"
        assert self.check.label
