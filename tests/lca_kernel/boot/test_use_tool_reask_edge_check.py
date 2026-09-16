"""Boot validation: act→think use_tool re-ask edge must be bounded.

Mirrors ``test_admit_recovery_edge_check.py`` for the tool re-ask path.
Without this check the kernel would silently accept an unbounded
``act.main → think.main`` re-ask (which turned into 880 empty think
turns in the 2026-09-16 stall).
"""

from __future__ import annotations

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import (
    EdgeLoopObligation,
    Plan,
    PlanEdge,
    PlanNode,
)
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca_kernel.boot.plan_validation.checks.use_tool_reask_edge import (
    UseToolReaskEdgeCheck,
)


def _outer_with_reask(
    *,
    bound: bool,
) -> Plan:
    reask = PlanEdge(
        source="act.main",
        target="think.main",
        when=Predicate(
            kind="and",
            children=(
                Predicate(
                    kind="eq",
                    port=PortRef(name="decision", field="action_type"),
                    value="use_tool",
                ),
                Predicate(
                    kind="in",
                    port=PortRef(name="approval_routing", field="next_hint"),
                    value=["approve_skipped"],
                ),
            ),
        ),
        loop=EdgeLoopObligation(max_iterations=8, budget="run.steps") if bound else None,
    )
    return Plan(
        id="phase.main.outer",
        nodes=(
            PlanNode(id="act.main", binding=BindingKind.NODE_EXECUTOR, entry=True),
            PlanNode(id="think.main", binding=BindingKind.NODE_EXECUTOR),
        ),
        edges=(reask,),
    )


def test_unbounded_reask_fails_loud() -> None:
    err = UseToolReaskEdgeCheck().run(_outer_with_reask(bound=False), plan_id="phase.main.outer")
    assert isinstance(err, PlanLiftError)
    assert "missing loop obligation" in str(err)


def test_bounded_reask_passes() -> None:
    err = UseToolReaskEdgeCheck().run(_outer_with_reask(bound=True), plan_id="phase.main.outer")
    assert err is None


def test_zero_max_iterations_fails_loud() -> None:
    """``EdgeLoopObligation`` itself rejects max_iterations <= 0 at
    model-construction time; the check is a defence-in-depth layer
    that catches hand-built edges (e.g. round-tripped from yaml).
    We expect a ValidationError from the plan construction.
    """
    import pytest
    from pydantic import ValidationError as PydValidationError

    with pytest.raises(PydValidationError):
        Plan(
            id="phase.main.outer",
            nodes=(
                PlanNode(id="act.main", binding=BindingKind.NODE_EXECUTOR, entry=True),
                PlanNode(id="think.main", binding=BindingKind.NODE_EXECUTOR),
            ),
            edges=(
                PlanEdge(
                    source="act.main",
                    target="think.main",
                    when=Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="action_type"),
                        value="use_tool",
                    ),
                    loop=EdgeLoopObligation(max_iterations=0, budget="run.steps"),
                ),
            ),
        )


def test_empty_budget_fails_loud() -> None:
    plan = Plan(
        id="phase.main.outer",
        nodes=(
            PlanNode(id="act.main", binding=BindingKind.NODE_EXECUTOR, entry=True),
            PlanNode(id="think.main", binding=BindingKind.NODE_EXECUTOR),
        ),
        edges=(
            PlanEdge(
                source="act.main",
                target="think.main",
                when=Predicate(
                    kind="eq",
                    port=PortRef(name="decision", field="action_type"),
                    value="use_tool",
                ),
                loop=EdgeLoopObligation(max_iterations=4, budget=""),
            ),
        ),
    )
    err = UseToolReaskEdgeCheck().run(plan, plan_id="phase.main.outer")
    assert isinstance(err, PlanLiftError)
    assert "budget" in str(err).lower()


def test_non_outer_plan_is_skipped() -> None:
    plan = Plan(
        id="inner.think",
        nodes=(PlanNode(id="x", binding=BindingKind.NODE_EXECUTOR, entry=True),),
        edges=(),
    )
    assert UseToolReaskEdgeCheck().run(plan, plan_id="inner.think") is None
