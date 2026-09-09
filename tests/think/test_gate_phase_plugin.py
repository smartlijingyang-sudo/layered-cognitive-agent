"""Tests for phase.think.gate plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
)
from lca.plugins.think.gate.plugin import ThinkGateExecutor


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
class _StubPhaseContext:
    plan_ref: str
    node_ref: str
    state: AgentState
    journal: Any
    budget: Any
    artifacts: dict[str, Any]
    capabilities: Any
    decision: Any
    observation: Any
    reflection: Any
    checkpoint_reason: Any

    def emit_fact(self, fact: Any) -> str:
        return ""

    def propose_delta(self, delta: Any) -> None:
        return None


def _ctx(caps: dict[str, Any], decision: Decision | None = None) -> _StubPhaseContext:
    artifacts: dict[str, Any] = {}
    if decision is not None:
        artifacts[CARRY_KEY] = ThinkSubgraphCarry(
            state=AgentState(trace_id="t", task="x", budget=Budget()),
            decision=decision,
        )
    return _StubPhaseContext(
        plan_ref="p",
        node_ref="think.gate",
        state=AgentState(trace_id="t", task="x", budget=Budget()),
        journal=None,
        budget=None,
        artifacts=artifacts,
        capabilities=caps,
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_gate_returns_enforced_decision() -> None:
    executor = ThinkGateExecutor()
    decision_in = _decision("dec_in")
    gate = _Gate(out=_decision("dec_out"))
    result = await executor.execute(
        _ctx({"phase.think.gate": gate}, decision=decision_in),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "decision"
    assert result.payload.decision_id == "dec_out"


@pytest.mark.asyncio
async def test_gate_applies_agent_gates_after_gate() -> None:
    """Order: phase.think.gate.enforce first, then phase.think.agent_gates.enforce."""
    executor = ThinkGateExecutor()
    decision_in = _decision("dec_in")
    primary = _Gate(out=_decision("dec_primary"))
    agent = _Gate(out=_decision("dec_agent"))
    result = await executor.execute(
        _ctx({"phase.think.gate": primary, "phase.think.agent_gates": agent}, decision=decision_in),
        PhaseInput(artifact=None),
    )
    assert result.payload.decision_id == "dec_agent"


@pytest.mark.asyncio
async def test_gate_without_decision_returns_input_artifact() -> None:
    executor = ThinkGateExecutor()
    sentinel = "fallback-input"
    result = await executor.execute(
        _ctx({"phase.think.gate": _Gate(out=_decision("dec_out"))}),
        PhaseInput(artifact=sentinel),
    )
    assert result.result_kind == "decision"
    assert result.payload == sentinel


@pytest.mark.asyncio
async def test_gate_without_gate_capability_passes_decision_through() -> None:
    executor = ThinkGateExecutor()
    decision_in = _decision("dec_in")
    result = await executor.execute(_ctx({}, decision=decision_in), PhaseInput(artifact=None))
    assert result.result_kind == "decision"
    assert result.payload is decision_in
