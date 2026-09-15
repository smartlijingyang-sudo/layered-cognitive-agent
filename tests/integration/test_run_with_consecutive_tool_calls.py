"""Regression: 5 consecutive identical tool calls must terminate via natural signals.

Spec mitigation per ``docs/superpowers/specs/2026-09-15-session-write-path-design.md`` §F:
without ``max_visits`` (deleted in PR1 / ADR-0225), the only termination
mechanism for tool-call loops is ``Decision(action_type=respond)`` and
``AgentState.budget``. A model that issues 5 identical tool calls in a
row must NOT trip ``budget_exceeded: node`` — that exit code is gone.

The failure mode this guards against is ``run_cc39610072bf``: a model
emitted the same ``echo "x"`` tool call 5 times in a row and the kernel
raised ``budget_exceeded`` instead of letting the model surface a final
``respond`` Decision. PR1 deletes ``max_visits`` so the safety net is
the natural terminal signal, not a per-node ceiling.

This test drives ``PlanInterpreter`` directly (no real LLM) using a
scripted :class:`NodeStrategy` that simulates the model's output:
first N-1 visits emit the same ``tool_call`` Decision; the Nth visit
emits the natural-exit ``respond`` Decision. The interpreter must
walk ``a -> a -> a -> a -> a -> b`` (5 visits to ``a``, 1 to ``b``)
and terminate cleanly.

Flow control uses edge predicates rather than the ``terminal_predicate``
on the plan node, because the predicate fires inside the visit and
would pre-empt edge selection. With typed edge predicates:

- ``a -> a`` matches while ``done`` is missing on ``a``'s port set.
- ``a -> b`` matches once ``done`` is present (the natural exit).
- ``b`` has no outgoing edges, so the plan terminates after one visit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.strategy import (
    NodeStrategy,
    StrategyContext,
)
from lca.framework.graph import (
    PlanInterpreter,
    PlanTraversal,
    StrategyRegistry,
)

# Visits to ``a`` before the natural-exit Decision fires. Mirrors the
# failure case in run_cc39610072bf: 5 identical tool calls in a row.
VISITS_BEFORE_NATURAL_EXIT = 5


def _build_plan() -> Plan:
    """Two-node plan: ``a`` (tool-call loop, exit via edge predicate) -> ``b``.

    Edge predicates (typed, ADR-0221 D4) select the next edge:

    - ``a -> a`` while ``done`` is missing on ``a``'s ports.
    - ``a -> b`` once ``done`` is present (natural exit).

    ``b`` has no outgoing edges, so the plan terminates after one visit.
    """
    return Plan(
        id="consecutive-tool-calls",
        nodes=(
            PlanNode(
                id="a",
                binding=BindingKind.TRANSFORM,
                entry=True,
            ),
            PlanNode(
                id="b",
                binding=BindingKind.TRANSFORM,
                terminal=True,
            ),
        ),
        edges=(
            PlanEdge(
                source="a",
                target="a",
                when=Predicate(kind="missing", port=PortRef(name="done"), value=None),
            ),
            PlanEdge(
                source="a",
                target="b",
                when=Predicate(kind="exists", port=PortRef(name="done"), value=True),
            ),
        ),
    )


def _scripted_strategy() -> NodeStrategy:
    """Single strategy that simulates the model on ``a`` and a passthrough on ``b``.

    For node ``a``:
      visits 1..N-1 emit the same ``tool_call`` Decision payload
      (mirroring ``Decision(tool_calls=[same_tool_same_args])``).
      The Nth visit emits the natural-exit ``respond`` Decision via
      the ``done`` port so the ``a -> b`` edge predicate matches.

    For node ``b``: passthrough ``response="done"`` and termination.
    """
    counter = {"n": 0}

    @dataclass(frozen=True, slots=True)
    class _Scripted(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(default_factory=NodeIOSchema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            if context.node_id == "a":
                counter["n"] += 1
                visit_n = counter["n"]
                if visit_n < VISITS_BEFORE_NATURAL_EXIT:
                    # N-1 identical tool calls: same tool name, same args,
                    # same shape. This is the loop body the model gets
                    # stuck on without ``Decision(respond)`` to break out.
                    tool_call_decision: dict[PortName, Any] = {
                        "tool_call": {
                            "name": "echo",
                            "args": {"text": "x"},
                            "call_id": "same-call-every-time",
                        }
                    }
                    return NodeOutput(
                        port_values=tool_call_decision,
                        producer_node=context.node_id,
                    )
                # Nth visit: the model emits the natural-exit respond
                # Decision. ``done=True`` triggers the ``a -> b`` edge
                # predicate so the interpreter leaves the loop instead
                # of looping back to ``a``.
                return NodeOutput(
                    port_values={"done": True, "response": "finished"},
                    producer_node=context.node_id,
                )
            # Node ``b``: passthrough response and terminate.
            return NodeOutput(
                port_values={"response": "done"},
                producer_node=context.node_id,
            )

    return _Scripted()


def _strategy_registry() -> StrategyRegistry:
    """Register the single scripted strategy (one per binding kind)."""
    registry = StrategyRegistry()
    registry.register(_scripted_strategy())
    return registry


async def test_five_consecutive_identical_tool_calls_terminate_naturally() -> None:
    """A self-looping ``a`` that emits 5 identical tool-call Decisions
    then a natural-exit ``respond`` Decision must terminate the plan
    via ``Decision(action_type=respond)``, NOT via a per-node
    ``budget_exceeded`` ceiling.

    Mirrors ``run_cc39610072bf``: 5 identical tool calls in a row.
    Without the deleted ``max_visits`` cap, the kernel relies on
    natural signals (the ``done=True`` port that makes the ``a -> b``
    edge predicate match).
    """
    plan = _build_plan()
    traversal = PlanTraversal(plan=plan)
    registry = _strategy_registry()
    interp = PlanInterpreter(registry=registry)
    result = await interp.run(plan, traversal=traversal)

    # The plan terminated (the kernel never hangs on a self-loop).
    assert traversal.terminated() is True
    assert result.terminal_node == "b"

    # The interpreter visited ``a`` exactly 5 times — proving the
    # self-loop ran to completion (not 2 or 3) and was broken by the
    # scripted 5th ``respond`` Decision, not by a ceiling.
    visits_to_a = [v for v in result.visits if v.node_id == "a"]
    visits_to_b = [v for v in result.visits if v.node_id == "b"]
    assert len(visits_to_a) == VISITS_BEFORE_NATURAL_EXIT, (
        f"self-loop must run exactly {VISITS_BEFORE_NATURAL_EXIT} times "
        f"before natural exit, got {len(visits_to_a)}"
    )
    assert len(visits_to_b) == 1, "exit node must be visited exactly once"

    # Spec §F: ``budget_exceeded: node`` is gone. No recorded visit
    # carries a ``budget_exceeded`` error.
    for visit in result.visits:
        if visit.error is not None:
            assert "budget_exceeded" not in str(visit.error).lower(), (
                f"unexpected budget_exceeded on visit to {visit.node_id}: {visit.error}"
            )


async def test_tool_call_loop_runs_full_count_with_identical_payloads() -> None:
    """Stronger guarantee: the loop body executes exactly
    ``VISITS_BEFORE_NATURAL_EXIT`` times before the natural-exit fires,
    and the first N-1 payloads are byte-identical (the failure shape
    of a model stuck repeating itself).

    Guards against a regression where a too-eager short-circuit (e.g.
    a hidden ``max_visits`` ceiling sneaking back into the kernel)
    caps the loop at fewer than the scripted 5 visits.
    """
    plan = _build_plan()
    traversal = PlanTraversal(plan=plan)
    registry = _strategy_registry()
    interp = PlanInterpreter(registry=registry)
    result = await interp.run(plan, traversal=traversal)

    # 5 visits to ``a`` + 1 visit to ``b`` = 6 recorded visits total.
    assert len(result.visits) == VISITS_BEFORE_NATURAL_EXIT + 1
    tool_call_visits = [
        v for v in result.visits if v.node_id == "a" and v.outputs.get("tool_call") is not None
    ]
    natural_exit_visits = [
        v for v in result.visits if v.node_id == "a" and v.outputs.get("done") is True
    ]
    assert len(tool_call_visits) == VISITS_BEFORE_NATURAL_EXIT - 1, (
        f"first {VISITS_BEFORE_NATURAL_EXIT - 1} visits must emit the identical tool-call Decision"
    )
    assert len(natural_exit_visits) == 1, (
        "exactly one visit must emit the natural-exit respond Decision"
    )
    # All identical tool calls have the same payload — that's the bug
    # shape (model stuck repeating itself).
    payloads = {repr(v.outputs["tool_call"]) for v in tool_call_visits}
    assert len(payloads) == 1, (
        f"expected {VISITS_BEFORE_NATURAL_EXIT - 1} identical tool calls, "
        f"got distinct payloads: {payloads}"
    )
