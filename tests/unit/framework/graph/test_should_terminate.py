"""PlanInterpreter honors ``RoutingDecision.should_terminate``.

A visit whose merged ports carry a terminating routing stops the whole
traversal before edge selection — inner and outer runs share this loop,
so the signal propagates across the subgraph seam. This is the pause
primitive the graph HITL path (``intervene.interrupt``) relies on: the
kernel persists the emitted ``Command`` and the run waits instead of
falling through to the next edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.protocols.graph.strategy import (
    NodeStrategy,
    StrategyContext,
)
from lca.framework.graph import (
    PlanInterpreter,
    PortRegistry,
    StrategyRegistry,
)


def _stop_routing() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.ASK_HUMAN,
        should_terminate=True,
        next_hint="intervene.resume",
    )


def _plan_pauser_then_after() -> Plan:
    return Plan(
        id="pause-test",
        nodes=(
            PlanNode(
                id="pauser",
                binding=BindingKind.TRANSFORM,
                entry=True,
                io_schema=NodeIOSchema(
                    outputs=(PortSpec(name=PortName("routing"), required=False),)
                ),
            ),
            PlanNode(
                id="after",
                binding=BindingKind.TRANSFORM,
                io_schema=NodeIOSchema(
                    outputs=(PortSpec(name=PortName("seen"), required=False),),
                ),
            ),
        ),
        edges=(PlanEdge(source="pauser", target="after"),),
    )


def _registry(visited: list[str], *, pauser_routing: RoutingDecision | None) -> StrategyRegistry:
    schema = NodeIOSchema(outputs=(PortSpec(name=PortName("routing"), required=False),))

    @dataclass(frozen=True, slots=True)
    class _Both(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            visited.append(context.node_id)
            if context.node_id == "pauser" and pauser_routing is not None:
                return NodeOutput(
                    port_values={"routing": pauser_routing},
                    producer_node=context.node_id,
                )
            return NodeOutput(port_values={}, producer_node=context.node_id)

    registry = StrategyRegistry()
    registry.register(_Both())
    return registry


async def test_terminating_routing_stops_before_next_edge() -> None:
    """The node after a pauser is never visited; terminal is the pauser."""
    visited: list[str] = []
    interp = PlanInterpreter(registry=_registry(visited, pauser_routing=_stop_routing()))
    result = await interp.run(_plan_pauser_then_after(), port_registry=PortRegistry())
    assert visited == ["pauser"]
    assert result.terminal_node == "pauser"
    assert isinstance(result.output.get("routing"), RoutingDecision)


async def test_non_terminating_routing_continues() -> None:
    """``should_terminate=False`` traverses normally (no behavior change)."""
    visited: list[str] = []
    plain = RoutingDecision(action_type=ActionType.RESPOND, should_terminate=False)
    interp = PlanInterpreter(registry=_registry(visited, pauser_routing=plain))
    result = await interp.run(_plan_pauser_then_after(), port_registry=PortRegistry())
    assert visited == ["pauser", "after"]
    assert result.terminal_node == "after"


async def test_stale_registry_routing_does_not_stop_new_visit() -> None:
    """Only the current visit's own ports can pause, never registry leftovers.

    A previous run that paused leaves ``routing`` in the shared registry;
    a new traversal whose first node emits nothing must still proceed.
    """
    ports = PortRegistry()
    visited: list[str] = []
    interp = PlanInterpreter(registry=_registry(visited, pauser_routing=_stop_routing()))
    await interp.run(_plan_pauser_then_after(), port_registry=ports)
    assert dict(ports.snapshot()).get("routing") is not None

    visited2: list[str] = []
    interp2 = PlanInterpreter(registry=_registry(visited2, pauser_routing=None))
    result = await interp2.run(_plan_pauser_then_after(), port_registry=ports)
    assert visited2 == ["pauser", "after"]
    assert result.terminal_node == "after"
