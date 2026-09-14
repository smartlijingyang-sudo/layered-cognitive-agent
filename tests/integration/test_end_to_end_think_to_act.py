"""Regression test for the silent-None predicate bug.

Pre-redesign, the v2 graph kernel's ``_ResultView.__getattr__`` returned
``None`` for any unknown attribute. Bundle edges like
``when: result.payload.decision.action_type == "use_tool"`` silently
evaluated to ``False`` even when the upstream decision was a USE_TOOL —
the kernel saw no matching edge, terminated the run, and the reducer
called ``apply_error → apply_stop`` with ``outcome=failure``.

Post-redesign, every cross-node read is a typed ``PortRef`` evaluated
against a typed ``PortReader``. The decision's ``action_type`` lives
on the typed ``RoutingDecision`` port; the typed ``Predicate`` reads
it directly. USE_TOOL decisions route to ``act.main``; non-USE_TOOL
decisions route elsewhere.

This test wires a minimal two-node plan (``think → act``) with a
typed ``Predicate`` and asserts that a USE_TOOL decision actually
fires the ``act.main`` node — i.e. the post-redesign kernel does not
regress to the silent-None bug.

If a future change re-introduces string-DSL predicates or a
silent-None ``__getattr__``, this test fails because act.main is never
visited.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import lift_graph_spec
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.framework.graph.strategy_registry import StrategyRegistry


# ---------------------------------------------------------------------------
# Test executors — record visits; think emits a USE_TOOL routing decision.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ThinkUseToolExecutor:
    """Think subgraph node: emit USE_TOOL routing + decision."""

    semantic_name: str = "think.stub.use_tool"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("decision", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context, input
        decision = Decision(
            decision_id="stub_use_tool",
            action_type=ActionType.USE_TOOL,
            rationale="use a tool",
            confidence=1.0,
            tool_calls=[],
            delegations=[],
        )
        return NodeOutput(
            port_values={
                "decision": decision,
                "routing": RoutingDecision(action_type=ActionType.USE_TOOL),
            }
        )


@dataclass(frozen=True, slots=True)
class _ThinkRespondExecutor:
    """Think subgraph node: emit RESPOND routing + decision."""

    semantic_name: str = "think.stub.respond"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("decision", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context, input
        decision = Decision(
            decision_id="stub_respond",
            action_type=ActionType.RESPOND,
            rationale="respond directly",
            confidence=1.0,
            tool_calls=[],
            delegations=[],
            response_text="hello",
        )
        return NodeOutput(
            port_values={
                "decision": decision,
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            }
        )


_ACT_VISITED: list[str] = []


@dataclass(frozen=True, slots=True)
class _ActRecorderExecutor:
    """Act subgraph node: record its visit; emit terminal routing."""

    semantic_name: str = "act.stub"
    region: str = "phase:act"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("act_outcome", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        _ACT_VISITED.append(context.metadata.get("node_id", "act.stub"))
        return NodeOutput(
            port_values={
                "act_outcome": {"status": "ok"},
                "routing": RoutingDecision(
                    action_type=ActionType.RESPOND, should_terminate=True
                ),
            }
        )


# ---------------------------------------------------------------------------
# Plan + registry helpers
# ---------------------------------------------------------------------------


def _make_registry(
    *, think_executor: object, include_act: bool = True
) -> StrategyRegistry:
    """Build a StrategyRegistry with NODE_EXECUTOR strategy + executor lookup."""
    registry = StrategyRegistry()
    lookup: dict[str, object] = {"think": think_executor}
    if include_act:
        lookup["act"] = _ActRecorderExecutor()

    def executor_lookup(
        *, binding: BindingKind, node_id: str, region: str | None
    ):
        if binding is not BindingKind.NODE_EXECUTOR:
            raise KeyError(f"unexpected binding {binding!r}")
        if node_id not in lookup:
            raise KeyError(f"no executor for node_id={node_id!r}")
        return lookup[node_id]

    registry.register(NodeExecutorStrategy(executor_lookup=executor_lookup))
    return registry


def _think_to_act_plan() -> dict[str, Any]:
    """Two-node plan: think → act on USE_TOOL; act is terminal.

    The edge ``when`` is a typed :class:`Predicate` reading the typed
    ``RoutingDecision.action_type`` from the source node's ``routing``
    port. Pre-redesign the string DSL
    ``when: result.payload.decision.action_type == "use_tool"``
    silently evaluated to False (the bug). Post-redesign the typed
    Predicate evaluates correctly.
    """
    return {
        "id": "think_to_act",
        "nodes": [
            {
                "id": "think",
                "binding": "node_executor",
                "outputs": ["decision", "routing"],
                "entry": True,
            },
            {
                "id": "act",
                "binding": "node_executor",
                "inputs": ["decision"],
                "outputs": ["act_outcome", "routing"],
                "terminal": True,
            },
        ],
        "edges": [
            {
                "from": "think",
                "to": "act",
                "when": {
                    "kind": "eq",
                    "port": {"name": "routing", "field": "action_type"},
                    "value": "use_tool",
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_use_tool_decision_routes_to_act_main() -> None:
    """A USE_TOOL decision must dispatch to act.main, not terminate.

    Pre-redesign this test would fail: the string DSL predicate
    silently returned None (False), the kernel had no matching edge,
    think.main terminated, and ``_ACT_VISITED`` stayed empty.
    """
    _ACT_VISITED.clear()
    spec = _think_to_act_plan()
    plan = lift_graph_spec(spec)
    registry = _make_registry(think_executor=_ThinkUseToolExecutor())

    interpreter = PlanInterpreter(registry=registry)
    result = asyncio.run(interpreter.run(plan, port_registry=PortRegistry()))

    assert "act" in _ACT_VISITED, (
        f"act node was not visited — typed predicate failed to route "
        f"USE_TOOL to act.main. visits={[v.node_id for v in result.visits]}"
    )
    visited_ids = [v.node_id for v in result.visits]
    assert visited_ids[-1] == "act", (
        f"act should be the terminal node, got sequence={visited_ids}"
    )


def test_respond_decision_does_not_route_to_act_main() -> None:
    """A RESPOND decision must terminate; act must NOT run.

    Negative control — the typed Predicate correctly routes only on
    USE_TOOL. If the predicate were to silently evaluate to True
    (the opposite silent-None bug), this test would fail because act
    would run unconditionally.
    """
    _ACT_VISITED.clear()
    spec = _think_to_act_plan()
    plan = lift_graph_spec(spec)
    registry = _make_registry(think_executor=_ThinkRespondExecutor())

    interpreter = PlanInterpreter(registry=registry)
    result = asyncio.run(interpreter.run(plan, port_registry=PortRegistry()))

    assert _ACT_VISITED == [], (
        f"act should NOT have been visited for a RESPOND decision; "
        f"got visits={_ACT_VISITED}"
    )
    visited_ids = [v.node_id for v in result.visits]
    assert visited_ids == ["think"], (
        f"expected single visit to think and termination; got {visited_ids}"
    )


def test_typed_predicate_is_used_not_string_dsl() -> None:
    """The lifted plan must carry a typed Predicate, not a string DSL.

    Belt-and-suspenders: even if a future refactor breaks runtime
    routing, this assertion catches the regression at lift time.
    """
    spec = _think_to_act_plan()
    plan = lift_graph_spec(spec)

    assert len(plan.edges) == 1
    edge = plan.edges[0]
    assert isinstance(edge.when, Predicate), (
        f"edge when: must be a typed Predicate, got {type(edge.when).__name__}"
    )
    assert edge.when.kind == "eq"
    assert isinstance(edge.when.port, PortRef)
    assert edge.when.port.name == "routing"
    assert edge.when.port.field == "action_type"
    assert edge.when.value == "use_tool"