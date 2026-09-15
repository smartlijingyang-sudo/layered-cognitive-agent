"""Tests for phase.think.budget.check plugin.

Verifies the typed ``budget.check`` node that reads ``state.budget``
via the ``Budget.exceeded`` SSOT and emits a ``RoutingDecision`` typed
port whose ``next_node`` steers the think waterfall either to
``think.context.compact`` (under cap) or ``terminal.commit`` (cap
tripped). Honors ADR-0225 (no per-node ``max_visits``).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.think.budget_check import ThinkBudgetCheckExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; budget.check node does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


@dataclass
class _StateStub:
    """Typed mock for ``AgentState`` exposing only ``budget``."""

    budget: Budget


def _state(budget: Budget) -> _StateStub:
    return _StateStub(budget=budget)


@pytest.mark.asyncio
async def test_budget_check_under_caps_continues_to_compact() -> None:
    """Under caps -> continue to ``think.context.compact``."""
    executor = ThinkBudgetCheckExecutor()
    budget = Budget(
        max_tokens=1000,
        max_cost_usd=1.0,
        max_steps=10,
        used_tokens=10,
        used_cost_usd=0.01,
        used_steps=1,
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"state": _state(budget)}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "think.context.compact"
    assert routing.should_terminate is False
    assert routing.next_hint == "budget_ok"


@pytest.mark.asyncio
async def test_budget_check_max_steps_exceeded_routes_to_terminal_commit() -> None:
    """``max_steps`` exceeded -> stop and route to ``terminal.commit``."""
    executor = ThinkBudgetCheckExecutor()
    budget = Budget(
        max_tokens=None,
        max_cost_usd=None,
        max_steps=3,
        used_tokens=0,
        used_cost_usd=0.0,
        used_steps=4,
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"state": _state(budget)}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.should_terminate is True
    assert routing.action_type == ActionType.STOP
    assert routing.next_hint == "budget_exceeded_steps"


@pytest.mark.asyncio
async def test_budget_check_max_tokens_exceeded_routes_to_terminal_commit() -> None:
    """``max_tokens`` exceeded -> stop and route to ``terminal.commit``."""
    executor = ThinkBudgetCheckExecutor()
    budget = Budget(
        max_tokens=100,
        max_cost_usd=None,
        max_steps=None,
        used_tokens=101,
        used_cost_usd=0.0,
        used_steps=0,
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"state": _state(budget)}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.should_terminate is True
    assert routing.action_type == ActionType.STOP
    assert routing.next_hint == "budget_exceeded_tokens"


@pytest.mark.asyncio
async def test_budget_check_is_idempotent() -> None:
    """Same ``state`` input -> identical ``routing`` across repeated calls.

    Strengthens the brief's "same state -> same routing" requirement
    (C9 idempotency). Also covers two fresh executor instances to prove
    no instance-level state leaks into subsequent outputs.
    """
    budget = Budget(
        max_tokens=50,
        max_cost_usd=None,
        max_steps=2,
        used_tokens=10,
        used_cost_usd=0.0,
        used_steps=1,
    )
    node_input = NodeInput(port_values={"state": _state(budget)})

    out_a = await ThinkBudgetCheckExecutor().node_execute(_ctx(), node_input)
    out_b = await ThinkBudgetCheckExecutor().node_execute(_ctx(), node_input)
    assert out_a.port_values["routing"] == out_b.port_values["routing"]

    out_c = await ThinkBudgetCheckExecutor().node_execute(_ctx(), node_input)
    out_d = await ThinkBudgetCheckExecutor().node_execute(_ctx(), node_input)
    assert out_c.port_values["routing"] == out_d.port_values["routing"]


@pytest.mark.asyncio
async def test_budget_check_first_exceeded_resource_wins() -> None:
    """When multiple caps are tripped, declaration order picks the reason.

    Declaration order is ``steps`` -> ``tokens`` -> ``cost_usd`` ->
    ``wall_clock_seconds``. This case trips steps + tokens; ``steps``
    must win so the trace is deterministic.
    """
    executor = ThinkBudgetCheckExecutor()
    budget = Budget(
        max_tokens=10,
        max_cost_usd=None,
        max_steps=1,
        used_tokens=20,
        used_cost_usd=0.0,
        used_steps=2,
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"state": _state(budget)}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.next_hint == "budget_exceeded_steps"


@pytest.mark.asyncio
async def test_budget_check_rejects_non_budget_state() -> None:
    """Missing or wrong-type ``state.budget`` must fail loudly, not silently pass."""
    executor = ThinkBudgetCheckExecutor()
    with pytest.raises(TypeError):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"state": object()}),
        )
