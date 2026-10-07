"""RA-023: ``max_steps`` -> graph loop bound translation (``clamp_loop_bounds``).

The run budget and the plan's per-edge ``loop.maxIterations`` count the
same thing (one bounded re-entry take == one agent iteration), so the
translation rule is ``min``: ``max_steps`` may only tighten a plan
bound, never loosen it. Plans are frozen pydantic models — the clamp
must copy, never mutate the compiled plan owned by the bindings.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import (
    EdgeLoopObligation,
    Plan,
    PlanEdge,
    PlanNode,
)
from lca.framework.graph.loop_budget import clamp_loop_bounds


def _plan(*edges: PlanEdge) -> Plan:
    nodes = (
        PlanNode(id="a", binding=BindingKind.NODE_EXECUTOR, entry=True),
        PlanNode(id="b", binding=BindingKind.NODE_EXECUTOR),
    )
    return Plan(id="p", nodes=nodes, edges=tuple(edges))


def _loop_edge(bound: int) -> PlanEdge:
    return PlanEdge(
        source="a",
        target="b",
        loop=EdgeLoopObligation(maxIterations=bound, budget="run.steps"),
    )


def test_clamp_tightens_loose_bound() -> None:
    plan = _plan(_loop_edge(24))
    clamped = clamp_loop_bounds(plan, max_steps=5)
    assert clamped is not plan
    assert clamped.edges[0].loop is not None
    assert clamped.edges[0].loop.max_iterations == 5
    # the frozen source plan is untouched
    assert plan.edges[0].loop is not None
    assert plan.edges[0].loop.max_iterations == 24


def test_clamp_never_loosens() -> None:
    plan = _plan(_loop_edge(1))
    assert clamp_loop_bounds(plan, max_steps=50) is plan


def test_clamp_equal_bound_is_noop() -> None:
    plan = _plan(_loop_edge(5))
    assert clamp_loop_bounds(plan, max_steps=5) is plan


def test_clamp_none_budget_returns_same_plan() -> None:
    plan = _plan(_loop_edge(24))
    assert clamp_loop_bounds(plan, max_steps=None) is plan


def test_clamp_ignores_edges_without_loop() -> None:
    plain = PlanEdge(source="a", target="b")
    plan = _plan(plain, _loop_edge(24))
    clamped = clamp_loop_bounds(plan, max_steps=5)
    assert clamped.edges[0] is plain
    assert clamped.edges[1].loop is not None
    assert clamped.edges[1].loop.max_iterations == 5
