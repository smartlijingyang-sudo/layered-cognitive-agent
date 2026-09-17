"""Tests for phase.think.budget.gate plugin (PR-B typed-port rewrite).

Verifies the typed ``budget.gate`` node that reads ``state.budget`` via
the whitelisted kernel runtime carrier and emits a ``RoutingDecision``
typed port whose ``next_node`` steers the think waterfall either to
``terminal.commit`` (cap tripped) or ``think.context.truncate`` (under
cap). Honors ADR-0225 (no per-node ``max_visits``).

Each of the four resources (``steps`` / ``tokens`` / ``cost_usd`` /
``wall_clock_seconds``) is exercised in both under- and over-cap
configurations so declaration-order tie breaks are observable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import utc_now
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.think.budget.threshold_gate import ThinkBudgetThresholdGateExecutor


class _RuntimeCarrier(dict):
    """Dict that also exposes attributes (the kernel runtime carrier shape)."""

    def __getattr__(self, name: str) -> object:
        return self.get(name)


def _ctx(state: AgentState) -> NodeContext:
    """The kernel runtime carrier carries ``state``; budget.gate reads it."""
    return NodeContext(runtime=_RuntimeCarrier(state=state), budget={}, metadata={})


def _budget(
    *,
    max_steps: int | None = 10,
    used_steps: int = 0,
    max_tokens: int | None = 1000,
    used_tokens: int = 0,
    max_cost_usd: float | None = 1.0,
    used_cost_usd: float = 0.0,
    max_wall_clock_seconds: float | None = 300.0,
    started_at: datetime | None = None,
) -> Budget:
    return Budget(
        max_steps=max_steps,
        used_steps=used_steps,
        max_tokens=max_tokens,
        used_tokens=used_tokens,
        max_cost_usd=max_cost_usd,
        used_cost_usd=used_cost_usd,
        max_wall_clock_seconds=max_wall_clock_seconds,
        started_at=started_at if started_at is not None else utc_now(),
    )


def _state_with(budget: Budget) -> AgentState:
    state = AgentState(trace_id="t-gate", task="", budget=budget)
    return state


@pytest.mark.asyncio
async def test_gate_under_all_caps_routes_to_context_truncate() -> None:
    """Under caps ⇒ continue to ``think.context.truncate`` (the truncate node)."""
    executor = ThinkBudgetThresholdGateExecutor()
    output = await executor.node_execute(_ctx(_state_with(_budget())), NodeInput(port_values={}))
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "think.context.truncate"
    assert routing.should_terminate is False
    assert routing.action_type == ActionType.RESPOND
    assert routing.next_hint == "budget_ok"


@pytest.mark.asyncio
async def test_gate_steps_exceeded_routes_to_terminal_commit() -> None:
    """``max_steps`` exceeded ⇒ stop, hint ``budget_exceeded_steps``."""
    executor = ThinkBudgetThresholdGateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(_budget(max_steps=3, used_steps=4))), NodeInput(port_values={})
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.should_terminate is True
    assert routing.action_type == ActionType.STOP
    assert routing.next_hint == "budget_exceeded_steps"


@pytest.mark.asyncio
async def test_gate_tokens_exceeded_routes_to_terminal_commit() -> None:
    """``max_tokens`` exceeded ⇒ stop, hint ``budget_exceeded_tokens``."""
    executor = ThinkBudgetThresholdGateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(_budget(max_tokens=100, used_tokens=101))), NodeInput(port_values={})
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.should_terminate is True
    assert routing.next_hint == "budget_exceeded_tokens"


@pytest.mark.asyncio
async def test_gate_cost_exceeded_routes_to_terminal_commit() -> None:
    """``max_cost_usd`` exceeded ⇒ stop, hint ``budget_exceeded_cost_usd``."""
    executor = ThinkBudgetThresholdGateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(_budget(max_cost_usd=1.0, used_cost_usd=1.5))), NodeInput(port_values={})
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.should_terminate is True
    assert routing.next_hint == "budget_exceeded_cost_usd"


@pytest.mark.asyncio
async def test_gate_wall_clock_exceeded_routes_to_terminal_commit() -> None:
    """``max_wall_clock_seconds`` exceeded ⇒ stop, hint
    ``budget_exceeded_wall_clock_seconds``.

    The Budget SSOT derives wall-clock from ``started_at``; this test
    backdates ``started_at`` to force an overage without depending on
    real wall-clock time.
    """
    executor = ThinkBudgetThresholdGateExecutor()
    old_started = utc_now() - timedelta(seconds=400)
    output = await executor.node_execute(
        _ctx(_state_with(_budget(max_wall_clock_seconds=300.0, started_at=old_started))),
        NodeInput(port_values={}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.should_terminate is True
    assert routing.next_hint == "budget_exceeded_wall_clock_seconds"
    harvest = output.port_values["decision"]
    assert harvest.action_type == ActionType.RESPOND.value
    assert harvest.response_text
    assert "budget_exceeded_wall_clock_seconds" in harvest.response_text
    assert "writeFile" in harvest.response_text


@pytest.mark.asyncio
async def test_gate_declaration_order_steps_wins_over_tokens() -> None:
    """When multiple caps trip on the same turn, ``steps`` wins the hint."""
    executor = ThinkBudgetThresholdGateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(_budget(max_steps=1, used_steps=2, max_tokens=10, used_tokens=20))),
        NodeInput(port_values={}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_hint == "budget_exceeded_steps"


@pytest.mark.asyncio
async def test_gate_declaration_order_tokens_wins_over_cost() -> None:
    """``tokens`` beats ``cost_usd`` in the declaration order."""
    executor = ThinkBudgetThresholdGateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(_budget(max_tokens=10, used_tokens=20, max_cost_usd=1.0, used_cost_usd=1.5))),
        NodeInput(port_values={}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_hint == "budget_exceeded_tokens"


@pytest.mark.asyncio
async def test_gate_no_state_in_runtime_raises() -> None:
    """No ``state`` on the runtime carrier ⇒ TypeError (fail-loud)."""
    executor = ThinkBudgetThresholdGateExecutor()
    with pytest.raises(TypeError, match="state"):
        await executor.node_execute(NodeContext(runtime={}, budget={}, metadata={}), NodeInput(port_values={}))


@pytest.mark.asyncio
async def test_gate_state_without_budget_raises() -> None:
    """``state`` present but missing ``.budget`` ⇒ TypeError (fail-loud)."""
    executor = ThinkBudgetThresholdGateExecutor()
    bad_state = AgentState(trace_id="t", task="", budget=Budget())  # default Budget is empty-ish
    # override to an invalid type
    object.__setattr__(bad_state, "budget", object())  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="budget"):
        await executor.node_execute(_ctx(bad_state), NodeInput(port_values={}))


@pytest.mark.asyncio
async def test_gate_is_idempotent() -> None:
    """Same ``state.budget`` ⇒ same routing across repeated calls (C9)."""
    state = _state_with(_budget(max_tokens=50, used_tokens=10, max_steps=2, used_steps=1))
    out_a = await ThinkBudgetThresholdGateExecutor().node_execute(_ctx(state), NodeInput(port_values={}))
    out_b = await ThinkBudgetThresholdGateExecutor().node_execute(_ctx(state), NodeInput(port_values={}))
    assert out_a.port_values["routing"] == out_b.port_values["routing"]
