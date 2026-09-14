"""Tests for :class:`PredicateWellformedCheck`.

Seven cases cover the decision tree:

- ``when: None`` (always-true edge) → pass (not a Predicate)
- simple ``eq`` with port + value → pass
- ``and`` with 1 child → reject (must have >=2 children)
- ``not`` with 2 children → reject (must have exactly 1 child)
- ``eq`` without value → reject (must carry a value)
- ``in`` with non-list value → reject (value must be list/tuple)
- ``exists`` with value → reject (must NOT carry a value)
"""
from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca_kernel.boot.plan_validation.checks.predicate_wellformed import (
    PredicateWellformedCheck,
)


def _node(
    node_id: str,
    *,
    entry: bool = False,
    terminal: bool = False,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        binding=BindingKind.NODE_EXECUTOR,
        entry=entry,
        terminal=terminal,
    )


def _plan(
    *nodes: PlanNode,
    edges: tuple[PlanEdge, ...] = (),
) -> Plan:
    return Plan(id="test.plan", nodes=tuple(nodes), edges=edges)


def _edge(when: Predicate | None) -> PlanEdge:
    return PlanEdge(source="a", target="b", when=when)


class TestPredicateWellformedCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = PredicateWellformedCheck()

    # ------------------------------------------------------------------
    # Case 1: when=None (always-true edge) → pass
    # ------------------------------------------------------------------

    def test_when_none_does_not_raise(self) -> None:
        """Edges without a Predicate (always-true) are out of scope."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(None),),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: simple eq with port + value → pass
    # ------------------------------------------------------------------

    def test_simple_eq_with_port_and_value_does_not_raise(self) -> None:
        """Well-formed leaf eq passes."""
        pred = Predicate(
            kind="eq", port=PortRef(name="score"), value=1
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 3: and with 1 child → reject
    # ------------------------------------------------------------------

    def test_and_with_one_child_raises(self) -> None:
        """and(a) is redundant — must have >=2 children."""
        leaf = Predicate(kind="eq", port=PortRef(name="x"), value=1)
        pred = Predicate(kind="and", children=(leaf,))
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.edge_id == "a->b"
        msg = str(err)
        assert "'and'" in msg
        assert "requires >=2 children" in msg

    def test_or_with_one_child_raises(self) -> None:
        """or(a) is redundant — same arity rule as and."""
        leaf = Predicate(kind="eq", port=PortRef(name="x"), value=1)
        pred = Predicate(kind="or", children=(leaf,))
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "'or'" in str(err)
        assert "requires >=2 children" in str(err)

    # ------------------------------------------------------------------
    # Case 4: not with 2 children → reject
    # ------------------------------------------------------------------

    def test_not_with_two_children_raises(self) -> None:
        """not(a, b) is ambiguous — must have exactly 1 child."""
        leaf1 = Predicate(kind="eq", port=PortRef(name="x"), value=1)
        leaf2 = Predicate(kind="eq", port=PortRef(name="y"), value=2)
        pred = Predicate(kind="not", children=(leaf1, leaf2))
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        assert err.edge_id == "a->b"
        assert "'not'" in str(err)
        assert "exactly 1 child" in str(err)

    def test_not_with_zero_children_raises(self) -> None:
        """not() is meaningless — same arity rule as not(a, b)."""
        pred = Predicate(kind="not", children=())
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "exactly 1 child" in str(err)

    # ------------------------------------------------------------------
    # Case 5: eq without value → reject
    # ------------------------------------------------------------------

    def test_eq_without_value_raises(self) -> None:
        """eq on a port needs a constant to compare against."""
        pred = Predicate(kind="eq", port=PortRef(name="score"))
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "'eq'" in str(err)
        assert "requires a value" in str(err)

    def test_ne_without_value_raises(self) -> None:
        """Same rule as eq."""
        pred = Predicate(kind="ne", port=PortRef(name="score"))
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "'ne'" in str(err)

    # ------------------------------------------------------------------
    # Case 6: in with non-list value → reject
    # ------------------------------------------------------------------

    def test_in_with_scalar_value_raises(self) -> None:
        """in(a, 1) is meaningless — value must be list/tuple."""
        pred = Predicate(kind="in", port=PortRef(name="x"), value=1)
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "'in'" in str(err)
        assert "must be a list" in str(err)
        assert "int" in str(err) or "1" in str(err)

    def test_in_with_tuple_value_does_not_raise(self) -> None:
        """Tuple is also a valid membership-test container."""
        pred = Predicate(
            kind="in",
            port=PortRef(name="x"),
            value=("a", "b"),
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 7: exists with value → reject
    # ------------------------------------------------------------------

    def test_exists_with_value_raises(self) -> None:
        """exists tests port presence, not value."""
        pred = Predicate(
            kind="exists", port=PortRef(name="done"), value=1
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "'exists'" in str(err)
        assert "should not have a value" in str(err)

    def test_missing_with_value_raises(self) -> None:
        """missing also tests presence only — same rule."""
        pred = Predicate(
            kind="missing", port=PortRef(name="done"), value=0
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "'missing'" in str(err)

    # ------------------------------------------------------------------
    # Recursion: error deep inside a nested combinator is surfaced.
    # ------------------------------------------------------------------

    def test_nested_combinator_error_is_reported(self) -> None:
        """A bad leaf inside ``and(a, eq-without-value)`` is still caught."""
        ok = Predicate(kind="eq", port=PortRef(name="x"), value=1)
        bad = Predicate(kind="eq", port=PortRef(name="y"))
        pred = Predicate(kind="and", children=(ok, bad))
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(_edge(pred),),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert "requires a value" in str(err)

    # ------------------------------------------------------------------
    # check_id / label are stable.
    # ------------------------------------------------------------------

    def test_check_id_and_label(self) -> None:
        assert self.check.check_id == "predicate_wellformed"
        assert self.check.label

    # ------------------------------------------------------------------
    # Empty / single-node plans and edges that loop across multiple
    # edges → only the first broken edge surfaces (one error per pass).
    # ------------------------------------------------------------------

    def test_first_bad_edge_is_reported(self) -> None:
        """Two edges; the first is malformed; the second is fine."""
        bad = Predicate(kind="not", children=())
        good = Predicate(
            kind="eq", port=PortRef(name="x"), value=1
        )
        plan = _plan(
            _node("a", entry=True),
            _node("b"),
            _node("c", terminal=True),
            edges=(
                PlanEdge(source="a", target="b", when=bad),
                PlanEdge(source="b", target="c", when=good),
            ),
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.edge_id == "a->b"

    def test_plan_without_edges_does_not_raise(self) -> None:
        """No edges → trivially passes."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
        )
        assert self.check.run(plan, plan_id="test.plan") is None
