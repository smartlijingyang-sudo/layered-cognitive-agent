"""Tests for :class:`MaxVisitsBoundsCheck`.

Six cases cover the two-tier bounds:

- max_visits=1, 10, 50 → pass (within recommended)
- max_visits=51 → reject (recommended exceeded)
- max_visits=1000 → reject (hard cap reached exactly)
- max_visits=99999 → reject (well past hard cap)
"""
from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanNode

from lca_kernel.boot.plan_validation.checks.max_visits_bounds import (
    MAX_VISITS_HARD_CAP,
    MAX_VISITS_RECOMMENDED,
    MaxVisitsBoundsCheck,
)


def _node(node_id: str, *, max_visits: int, entry: bool = False) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        config={},
        max_visits=max_visits,
        terminal=False,
        entry=entry,
        subgraph_ref=None,
        io_schema=NodeIOSchema(),
    )


def _plan(*nodes: PlanNode) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes), edges=())


class TestMaxVisitsBoundsCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = MaxVisitsBoundsCheck()

    # ------------------------------------------------------------------
    # Case 1: max_visits=1 → pass
    # ------------------------------------------------------------------

    def test_max_visits_one_does_not_raise(self) -> None:
        plan = _plan(_node("a", max_visits=1, entry=True))
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: max_visits=10 → pass
    # ------------------------------------------------------------------

    def test_max_visits_ten_does_not_raise(self) -> None:
        plan = _plan(_node("a", max_visits=10, entry=True))
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 3: max_visits=50 → pass (recommended boundary)
    # ------------------------------------------------------------------

    def test_max_visits_at_recommended_does_not_raise(self) -> None:
        plan = _plan(_node("a", max_visits=MAX_VISITS_RECOMMENDED, entry=True))
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 4: max_visits=51 → reject (recommended exceeded)
    # ------------------------------------------------------------------

    def test_max_visits_above_recommended_raises(self) -> None:
        plan = _plan(_node("a", max_visits=51, entry=True))
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "max_visits=51" in msg
        assert "recommended" in msg
        assert str(MAX_VISITS_RECOMMENDED) in msg

    # ------------------------------------------------------------------
    # Case 5: max_visits=1000 → reject (boundary at hard cap; goes to
    # recommended-tier message because the check uses strict ``>``)
    # ------------------------------------------------------------------

    def test_max_visits_at_hard_cap_raises(self) -> None:
        plan = _plan(_node("a", max_visits=MAX_VISITS_HARD_CAP, entry=True))
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "max_visits=1000" in msg
        # 1000 == hard cap exactly, so the recommended-tier message fires.
        assert "recommended" in msg
        assert "hard cap" not in msg

    # ------------------------------------------------------------------
    # Case 6: max_visits=99999 → reject (way over hard cap)
    # ------------------------------------------------------------------

    def test_max_visits_way_over_hard_cap_raises(self) -> None:
        plan = _plan(_node("a", max_visits=99999, entry=True))
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "max_visits=99999" in msg
        assert "hard cap" in msg
