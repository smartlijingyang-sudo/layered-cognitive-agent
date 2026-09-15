"""Tests for phase.think.route.decide plugin.

Verifies the typed ``route.decide`` node that replaces two
``when: { kind: missing | exists, port: decision }`` edge predicates.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.think.route.decide import ThinkRouteDecideExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; decide node does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


@pytest.mark.asyncio
async def test_route_decide_short_circuits_on_present_decision() -> None:
    executor = ThinkRouteDecideExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": {"action_type": "respond"}}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.action_type == ActionType.SHORT_CIRCUIT
    assert routing.next_node == "think.gate"


@pytest.mark.asyncio
async def test_route_decide_falls_through_on_missing_decision() -> None:
    executor = ThinkRouteDecideExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.action_type == ActionType.RESPOND
    assert routing.next_node == "think.route"


@pytest.mark.asyncio
async def test_route_decide_is_idempotent() -> None:
    executor = ThinkRouteDecideExecutor()
    input_present = NodeInput(port_values={"decision": {"action_type": "respond"}})
    out1 = await executor.node_execute(_ctx(), input_present)
    out2 = await executor.node_execute(_ctx(), input_present)
    assert out1.port_values["routing"] == out2.port_values["routing"]

    input_absent = NodeInput(port_values={})
    out3 = await executor.node_execute(_ctx(), input_absent)
    out4 = await executor.node_execute(_ctx(), input_absent)
    assert out3.port_values["routing"] == out4.port_values["routing"]


@pytest.mark.asyncio
async def test_route_decide_is_pure_across_instances() -> None:
    """Two separately-constructed executors must agree on the same input.

    Strengthens the brief's "no hidden state" requirement: equality across
    fresh instances proves the executor carries no instance-level state that
    leaks into subsequent outputs.
    """
    input_present = NodeInput(port_values={"decision": {"action_type": "respond"}})
    out_a = await ThinkRouteDecideExecutor().node_execute(_ctx(), input_present)
    out_b = await ThinkRouteDecideExecutor().node_execute(_ctx(), input_present)
    assert out_a.port_values["routing"] == out_b.port_values["routing"]

    input_absent = NodeInput(port_values={})
    out_c = await ThinkRouteDecideExecutor().node_execute(_ctx(), input_absent)
    out_d = await ThinkRouteDecideExecutor().node_execute(_ctx(), input_absent)
    assert out_c.port_values["routing"] == out_d.port_values["routing"]


@pytest.mark.asyncio
async def test_route_decide_next_node_is_string() -> None:
    executor = ThinkRouteDecideExecutor()

    out_present = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": {"action_type": "respond"}}),
    )
    routing_present: RoutingDecision = out_present.port_values["routing"]
    assert isinstance(routing_present.next_node, str)

    out_absent = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={}),
    )
    routing_absent: RoutingDecision = out_absent.port_values["routing"]
    assert isinstance(routing_absent.next_node, str)
