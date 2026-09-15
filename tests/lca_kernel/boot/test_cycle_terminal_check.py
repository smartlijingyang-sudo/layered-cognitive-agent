"""Tests for :class:`CycleHasTerminalCheck`.

Six cases cover the design:

- 2-node cycle without terminal → reject (infinite loop trap)
- 2-node cycle with one terminal → pass
- 3-node SCC all non-terminal → reject (lists all 3 nodes)
- Single-node SCC (self-loop) → pass (handled by SelfLoopSafeCheck)
- Linear plan (a→b→c, c terminal) → pass
- Cycle with terminal_predicate node → pass (predicate counts as terminal)
"""
from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.predicate import PortRef, Predicate

from lca_kernel.boot.plan_validation.checks.cycle_terminal import (
    CycleHasTerminalCheck,
)


def _node(
    node_id: str,
    *,
    entry: bool = False,
    terminal: bool = False,
    io_schema: NodeIOSchema | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        config={},
        terminal=terminal,
        entry=entry,
        subgraph_ref=None,
        io_schema=io_schema if io_schema is not None else NodeIOSchema(),
    )


def _plan(*nodes: PlanNode, edges: tuple[PlanEdge, ...] = ()) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes), edges=edges)


class TestCycleHasTerminalCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = CycleHasTerminalCheck()

    # ------------------------------------------------------------------
    # Case 1: 2-node cycle without terminal → reject
    # ------------------------------------------------------------------

    def test_two_node_cycle_no_terminal_raises(self) -> None:
        """a→b→a with no terminal is an infinite loop trap."""
        plan = _plan(
            _node("a", entry=True),
            _node("b"),
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
        assert "no terminal node" in msg

    # ------------------------------------------------------------------
    # Case 2: 2-node cycle with one terminal → pass
    # ------------------------------------------------------------------

    def test_two_node_cycle_with_terminal_does_not_raise(self) -> None:
        """a→b→a with b.terminal=True is safe."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 3: 3-node SCC all non-terminal → reject
    # ------------------------------------------------------------------

    def test_three_node_scc_no_terminal_raises(self) -> None:
        """a→b→c→a with no terminal lists all 3 nodes in the error."""
        plan = _plan(
            _node("a", entry=True),
            _node("b"),
            _node("c"),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="c"),
                PlanEdge(source="c", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "b" in msg
        assert "c" in msg
        # scc_names is sorted — error should list all three
        assert "no terminal node" in msg

    # ------------------------------------------------------------------
    # Case 4: Single-node SCC (self-loop) → pass
    # ------------------------------------------------------------------

    def test_single_node_self_loop_does_not_raise(self) -> None:
        """Self-loop is handled by SelfLoopSafeCheck, not this check."""
        plan = _plan(
            _node("a", entry=True),
            edges=(PlanEdge(source="a", target="a"),),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 5: Linear plan (a→b→c, c terminal) → pass
    # ------------------------------------------------------------------

    def test_linear_plan_does_not_raise(self) -> None:
        """No cycles at all — trivially passes."""
        plan = _plan(
            _node("a", entry=True),
            _node("b"),
            _node("c", terminal=True),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="c"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 6: terminal_predicate counts as terminal → pass
    # ------------------------------------------------------------------

    def test_terminal_predicate_counts_as_terminal(self) -> None:
        """A node with terminal_predicate (not node.terminal) satisfies the check."""
        pred = Predicate(kind="exists", port=PortRef(name="done"))
        io_schema = NodeIOSchema(
            inputs=(),
            outputs=(),
            terminal_predicate=pred,
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", io_schema=io_schema),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        assert self.check.run(plan, plan_id="test.plan") is None
