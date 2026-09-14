"""Tests for :class:`MaxVisitsVsSccCheck`.

Each node's ``max_visits`` must be at least the size of its strongly
connected component — otherwise the interpreter hits budget_exceeded
on cycle entry before the cycle reaches its natural terminal.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode

from lca_kernel.boot.plan_validation.checks.max_visits_vs_scc import (
    MaxVisitsVsSccCheck,
)


def _node(node_id, *, max_visits=1, terminal=False, entry=False, sub_ref=None):
    return PlanNode(
        id=node_id,
        binding=BindingKind.TERMINATE if terminal else BindingKind.NODE_EXECUTOR,
        io_schema=NodeIOSchema(),
        config={},
        max_visits=max_visits,
        terminal=terminal,
        entry=entry,
        subgraph_ref=sub_ref,
    )


def _plan(*nodes, edges):
    return Plan(
        id="test.max_visits_vs_scc",
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


class TestMaxVisitsVsSccCheck:
    def setup_method(self) -> None:
        self.check = MaxVisitsVsSccCheck()
        self.plan_id = "test.max_visits_vs_scc"

    def test_linear_plan_with_max_visits_1_does_not_raise(self) -> None:
        """Linear plan: each node SCC size=1, max_visits=1 fine."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(
                PlanEdge(source="a", target="b"),
            ),
        )
        err = self.check.run(plan, plan_id=self.plan_id)
        assert err is None

    def test_two_node_cycle_max_visits_2_does_not_raise(self) -> None:
        """A→B→A cycle (size 2) with max_visits=2 each converges cleanly."""
        plan = _plan(
            _node("a", entry=True, max_visits=2),
            _node("b", max_visits=2),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id=self.plan_id)
        assert err is None

    def test_two_node_cycle_max_visits_1_raises(self) -> None:
        """A→B→A with max_visits=1 — interpreter would hit budget on entry."""
        plan = _plan(
            _node("a", entry=True, max_visits=1),
            _node("b", max_visits=1),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id=self.plan_id)
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == self.plan_id
        assert "max_visits=1" in str(err)
        assert "size 2" in str(err)

    def test_three_node_scc_raises_on_low_max_visits(self) -> None:
        """A→B→C→A (size 3); max_visits=2 < 3 raises."""
        plan = _plan(
            _node("a", entry=True, max_visits=2),
            _node("b", max_visits=2),
            _node("c", max_visits=2),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="c"),
                PlanEdge(source="c", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id=self.plan_id)
        assert isinstance(err, PlanLiftError)
        assert "size 3" in str(err)

    def test_single_node_scc_with_self_loop_does_not_raise(self) -> None:
        """a→a self-loop is its own SCC of size 1, max_visits=1 fine."""
        plan = _plan(
            _node("a", entry=True, max_visits=1),
            _node("b", terminal=True),
            edges=(
                PlanEdge(source="a", target="a"),
                PlanEdge(source="a", target="b"),
            ),
        )
        err = self.check.run(plan, plan_id=self.plan_id)
        assert err is None

    def test_terminal_node_inside_cycle_still_passes(self) -> None:
        """Terminal inside SCC: SCC size still counts the terminal."""
        plan = _plan(
            _node("a", entry=True, max_visits=2),
            _node("b", max_visits=2, terminal=True),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="a"),
            ),
        )
        err = self.check.run(plan, plan_id=self.plan_id)
        assert err is None

    def test_empty_plan_does_not_raise(self) -> None:
        plan = Plan(id=self.plan_id, nodes=(), edges=())
        err = self.check.run(plan, plan_id=self.plan_id)
        assert err is None

    def test_check_id_and_label(self) -> None:
        assert MaxVisitsVsSccCheck.check_id == "max_visits_vs_scc"
        assert "max_visits" in MaxVisitsVsSccCheck.label.lower()
