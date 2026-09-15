"""Regression tests for PR1: ``max_visits`` is gone from the v2 graph kernel.

Per ADR-0225 (drop max_visits graph-topology invariant): the field
and kwarg no longer exist on ``PlanNode`` / ``PlanTraversal.visit``.
The interpreter never emits ``budget_exceeded`` — natural termination
is via ``Decision(action_type=respond)``, ``should_terminate`` from
act.observe, and ``AgentState.budget`` (max_steps / max_wall_clock /
max_tokens).

This file pins the deletion. It must be deleted in the same PR per
AGENTS.md §4 (delete-when condition).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.framework.graph.traversal import PlanTraversal


def test_plan_node_has_no_max_visits_field():
    """PlanNode has no ``max_visits`` attribute.

    ADR-0225: the per-node visit counter is gone. ``hasattr`` is the
    load-bearing assertion — pydantic model fields appear in
    ``model_fields`` and as instance attributes; we verify the public
    surface no longer exposes the name.
    """
    node = PlanNode(id="a", binding=BindingKind.NODE_EXECUTOR)
    assert not hasattr(node, "max_visits")
    assert "max_visits" not in type(node).model_fields


def test_plan_traversal_visit_no_max_visits_kwarg():
    """``PlanTraversal.visit`` no longer accepts a ``max_visits`` kwarg.

    The visit counter is still tracked (the resume-path uses it), but
    no longer capped at a per-node ceiling.
    """
    params = inspect.signature(PlanTraversal.visit).parameters
    assert "max_visits" not in params


@pytest.mark.asyncio
async def test_interpreter_does_not_emit_budget_exceeded_error():
    """Regression for run_cc39610072bf: budget_exceeded is no longer produced.

    A self-looping plan that runs the same node 3+ times must
    terminate via the natural signal (here: ``terminal_predicate``
    after the strategy emits the ``done`` port) — never via a
    per-node budget cap. ``terminal_reason`` is ``None`` because the
    kernel did not set it; the kernel only sets it on explicit
    termination paths (``terminal_predicate`` match, edge=None
    advance, etc.).
    """
    term_pred = Predicate(kind="exists", port=PortRef(name="done"), value=True)

    @dataclass(frozen=True, slots=True)
    class _Stub(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(
            default_factory=lambda: NodeIOSchema(terminal_predicate=term_pred)
        )

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            counter.append("a")
            emit: dict[PortName, Any] = {"done": True} if len(counter) >= 2 else {}
            return NodeOutput(port_values=emit, producer_node=context.node_id)

    counter: list[str] = []
    plan = Plan(
        id="loop-plan",
        nodes=(
            PlanNode(
                id="a",
                binding=BindingKind.TRANSFORM,
                entry=True,
                io_schema=NodeIOSchema(terminal_predicate=term_pred),
            ),
        ),
        edges=(PlanEdge(source="a", target="a"),),
    )

    registry = StrategyRegistry()
    registry.register(_Stub())
    interp = PlanInterpreter(registry=registry)
    result = await interp.run(plan)

    # The interpreter terminated via terminal_predicate — assert
    # budget_exceeded was never the trigger.
    assert len(counter) >= 2, "self-loop should have run at least twice"
    assert result.visits, "interpreter recorded zero visits — self-loop did not run"
    # None of the recorded visits should mention ``budget_exceeded``:
    # the kernel never trips a per-node ceiling.
    assert all(
        visit.error is None or "budget_exceeded" not in str(visit.error).lower()
        for visit in result.visits
    )
    # A fresh traversal never pre-sets terminal_reason.
    fresh = PlanTraversal(plan=plan)
    assert fresh.terminal_reason is None
