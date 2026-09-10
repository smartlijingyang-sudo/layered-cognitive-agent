"""Tests for phase.think.local_gate plugin (post-PhaseExecutor removal)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.plugins.think.local_gate import ThinkLocalGateExecutor


def _decision(decision_id: str = "dec_x") -> Decision:
    return Decision(  # type: ignore[call-arg]
        decision_id=decision_id,
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )


@dataclass
class _LocalGate:
    """Fake DecisionGate matching the Protocol signature."""

    out: Decision

    async def enforce(self, state, decision: Decision) -> Decision:
        return self.out


@dataclass
class _StubRuntime:
    state: Any
    agent_gates: Any


def _make(caps: dict[str, Any], decision: Decision | None = None) -> tuple[NodeContext, NodeInput]:
    from lca.contracts.models.core.state.state import AgentState, Budget
    runtime = _StubRuntime(state=AgentState(trace_id="t", task="x", budget=Budget()), agent_gates=caps.get("agent_gates"))
    port_values: dict[str, Any] = {}
    if decision is not None:
        port_values["decision"] = decision
    return (
        NodeContext(runtime=runtime, budget={"max_visits": 1}, metadata={}),
        NodeInput(port_values=port_values),
    )


@pytest.mark.asyncio
async def test_local_gate_enforces_decision_and_emits_enforced() -> None:
    """Happy path: enforce decision via local DecisionGate, emit enforced decision."""
    executor = ThinkLocalGateExecutor()
    decision_in = _decision("dec_in")
    gate = _LocalGate(out=_decision("dec_local"))
    context, input_ = _make({"agent_gates": gate}, decision=decision_in)
    result = await executor.node_execute(context=context, input=input_)
    assert isinstance(result, NodeOutput)
    assert "enforced_decision" in result.port_values
    enforced = result.port_values["enforced_decision"]
    assert isinstance(enforced, Decision)
    assert enforced.decision_id == "dec_local"


@pytest.mark.asyncio
async def test_local_gate_does_not_consult_other_capabilities() -> None:
    """local_gate only reads agent_gates; other capabilities are ignored."""
    executor = ThinkLocalGateExecutor()
    decision_in = _decision("dec_in")
    local = _LocalGate(out=_decision("dec_local"))
    other = _LocalGate(out=_decision("dec_other_should_be_ignored"))
    context, input_ = _make(
        {"agent_gates": local, "other_capability": other}, decision=decision_in
    )
    result = await executor.node_execute(context=context, input=input_)
    enforced = result.port_values["enforced_decision"]
    assert enforced.decision_id == "dec_local"


@pytest.mark.asyncio
async def test_local_gate_without_decision_returns_empty_output() -> None:
    """No candidate decision → empty port_values (no enforced decision)."""
    executor = ThinkLocalGateExecutor()
    context, input_ = _make({"agent_gates": _LocalGate(out=_decision("dec_out"))})
    result = await executor.node_execute(context=context, input=input_)
    assert result.port_values == {}


@pytest.mark.asyncio
async def test_local_gate_without_capability_passes_decision_through() -> None:
    """No agent_gates capability → enforced_decision = input decision (passthrough)."""
    executor = ThinkLocalGateExecutor()
    decision_in = _decision("dec_in")
    context, input_ = _make({}, decision=decision_in)
    result = await executor.node_execute(context=context, input=input_)
    assert result.port_values["enforced_decision"] == decision_in
    assert result.port_values["think_signal"] == "local_gated"