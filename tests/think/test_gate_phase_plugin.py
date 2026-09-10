"""Tests for phase.think.gate plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.plugins.think.gate import ThinkGateExecutor


def _decision(decision_id: str = "dec_in") -> Decision:
    return Decision(  # type: ignore[call-arg]
        decision_id=decision_id,
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )


@dataclass
class _Gate:
    out: Decision

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        return self.out


@dataclass
class _StubRuntime:
    state: AgentState | None
    decision_gate: Any


def _ctx(caps: dict[str, Any], decision: Decision | None = None) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        decision_gate=caps.get("phase.think.gate"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


@pytest.mark.asyncio
async def test_gate_returns_enforced_decision() -> None:
    executor = ThinkGateExecutor()
    decision_in = _decision("dec_in")
    gate = _Gate(out=_decision("dec_out"))
    result = await executor.node_execute(
        _ctx({"phase.think.gate": gate}, decision=decision_in),
        NodeInput(port_values={"decision": decision_in}),
    )
    assert result.port_values.get("enforced_decision").decision_id == "dec_out"


@pytest.mark.asyncio
async def test_gate_without_decision_returns_empty_ports() -> None:
    executor = ThinkGateExecutor()
    result = await executor.node_execute(
        _ctx({"phase.think.gate": _Gate(out=_decision("dec_out"))}, decision=None),
        NodeInput(port_values={}),
    )
    assert result.port_values == {}


@pytest.mark.asyncio
async def test_gate_without_gate_capability_passes_decision_through() -> None:
    executor = ThinkGateExecutor()
    decision_in = _decision("dec_in")
    result = await executor.node_execute(
        _ctx({}, decision=decision_in),
        NodeInput(port_values={"decision": decision_in}),
    )
    assert result.port_values.get("enforced_decision") is decision_in