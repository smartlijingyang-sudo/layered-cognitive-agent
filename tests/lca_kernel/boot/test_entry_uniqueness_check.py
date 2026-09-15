"""Tests for :class:`EntryUniquenessCheck`.

Four cases cover the design:

- 0 entry → pass (lifter + ``_validate_termination`` own the
  no-entry diagnostic; this check does not double-report)
- 1 entry → pass
- 2 entry → reject, error mentions both node ids
- 3 entry → reject, error lists all three

Construction note
-----------------

``Plan`` carries an ``@model_validator`` that rejects 0 and >1
entries at construction time, and the model is frozen, so we
bypass the validator with :meth:`Plan.model_construct` to build
the pathological cases.  This mirrors the convention used in
:mod:`tests.framework.graph.test_plan_lift` for the
no-termination case — the check exists precisely to catch the
pathological shape that the model validator would otherwise hide
behind a raw ``pydantic_core.ValidationError``.
"""
from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode

from lca_kernel.boot.plan_validation.checks.entry_uniqueness import (
    EntryUniquenessCheck,
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
        config={},
        terminal=terminal,
        entry=entry,
        subgraph_ref=None,
        io_schema=NodeIOSchema(),
    )


def _plan(
    *nodes: PlanNode,
    edges: tuple[PlanEdge, ...] = (),
    bypass: bool = False,
) -> Plan:
    """Build a plan; with ``bypass=True`` skip the model validator.

    The default path is the normal constructor — used for the
    well-formed cases.  The bypass path is :meth:`Plan.model_construct`
    so we can hand the check the pathological shapes (0 / >1 entry)
    that the model validator would otherwise refuse to build.
    """
    if bypass:
        return Plan.model_construct(
            id="test.plan",
            nodes=tuple(nodes),
            edges=edges,
            approval_resume_node=None,
            declared_inputs=(),
        )
    return Plan(id="test.plan", nodes=tuple(nodes), edges=edges)


class TestEntryUniquenessCheck:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.check = EntryUniquenessCheck()

    # ------------------------------------------------------------------
    # Case 1: 0 entry → pass (lifter owns the no-entry diagnostic)
    # ------------------------------------------------------------------

    def test_zero_entry_does_not_raise(self) -> None:
        """No node marked entry is handled elsewhere; this check stays silent."""
        plan = _plan(
            _node("a"),
            _node("b", terminal=True),
            edges=(PlanEdge(source="a", target="b"),),
            bypass=True,
        )
        assert plan.nodes and not any(n.entry for n in plan.nodes)
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 2: 1 entry → pass
    # ------------------------------------------------------------------

    def test_one_entry_does_not_raise(self) -> None:
        """The canonical case — exactly one entry node."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", terminal=True),
            edges=(PlanEdge(source="a", target="b"),),
        )
        assert self.check.run(plan, plan_id="test.plan") is None

    # ------------------------------------------------------------------
    # Case 3: 2 entry → reject, both ids surfaced
    # ------------------------------------------------------------------

    def test_two_entry_raises_and_lists_both(self) -> None:
        """Two nodes marked entry=True is the exact bug this check catches."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", entry=True),
            _node("c", terminal=True),
            edges=(
                PlanEdge(source="a", target="c"),
                PlanEdge(source="b", target="c"),
            ),
            bypass=True,
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "b" in msg
        assert "multiple entry nodes" in msg
        assert "exactly one entry is required" in msg

    # ------------------------------------------------------------------
    # Case 4: 3 entry → reject, all three ids surfaced
    # ------------------------------------------------------------------

    def test_three_entry_raises_and_lists_all(self) -> None:
        """All three offending ids appear in the error message."""
        plan = _plan(
            _node("a", entry=True),
            _node("b", entry=True),
            _node("c", entry=True),
            edges=(),
            bypass=True,
        )
        err = self.check.run(plan, plan_id="test.plan")
        assert isinstance(err, PlanLiftError)
        assert err.plan_id == "test.plan"
        msg = str(err)
        assert "a" in msg
        assert "b" in msg
        assert "c" in msg
        assert "multiple entry nodes" in msg
