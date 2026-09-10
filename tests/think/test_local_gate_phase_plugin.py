"""Tests for phase.think.local_gate plugin.

Part of PR-2 think subgraph decompress (Task 2). The local_gate step
extracts the per-think half of the original ``phase.think.gate``:
it reads the ``phase.think.local_gate`` capability and enforces the
current Decision via the local DecisionGate.

Differences from the legacy ``gate`` step:
- Reads capability key ``phase.think.local_gate`` (not ``gate``).
- Returns ``result_kind="think_stage"`` (intermediate, not terminal).
- Emits the enforced Decision via the carry, not via ``result.payload``.

The terminal sink (``phase.think.verdict_emit``) and the plan-bound
gate (``phase.think.agent_gate``) live in their own nodes; this step
owns ONLY the per-think local enforce.
"""

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
from lca.plugins.think.local_gate.plugin import ThinkLocalGateExecutor


def _decision(decision_id: str = "dec_in") -> Decision:
    return Decision(  # type: ignore[call-arg]
        decision_id=decision_id,
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )


@dataclass
class _LocalGate:
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
        node_ref="think.local_gate",
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
async def test_local_gate_enforces_decision_and_passes_carry() -> None:
    """Happy path: enforce decision and emit updated carry as intermediate."""
    executor = ThinkLocalGateExecutor()
    decision_in = _decision("dec_in")
    gate = _LocalGate(out=_decision("dec_local"))
    result = await executor.execute(
        _ctx({"phase.think.local_gate": gate}, decision=decision_in),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    # The enforced decision lives on the carry, not on result.payload.
    assert isinstance(result.payload, ThinkSubgraphCarry)
    assert result.payload.decision is not None
    assert result.payload.decision.decision_id == "dec_local"


@pytest.mark.asyncio
async def test_local_gate_does_not_consult_agent_gates() -> None:
    """local_gate is per-think only; agent_gates belong to a separate node (agent_gate)."""
    executor = ThinkLocalGateExecutor()
    decision_in = _decision("dec_in")
    local = _LocalGate(out=_decision("dec_local"))
    # agent_gates registered but MUST be ignored by local_gate.
    agent = _LocalGate(out=_decision("dec_agent_should_be_ignored"))
    result = await executor.execute(
        _ctx(
            {"phase.think.local_gate": local, "phase.think.agent_gates": agent},
            decision=decision_in,
        ),
        PhaseInput(artifact=None),
    )
    assert result.payload.decision.decision_id == "dec_local"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_local_gate_without_decision_returns_input_artifact() -> None:
    """No candidate decision → terminal fallback (matches legacy gate contract)."""
    executor = ThinkLocalGateExecutor()
    sentinel = "fallback-input"
    result = await executor.execute(
        _ctx({"phase.think.local_gate": _LocalGate(out=_decision("dec_out"))}),
        PhaseInput(artifact=sentinel),
    )
    assert result.result_kind == "decision"
    assert result.payload == sentinel


@pytest.mark.asyncio
async def test_local_gate_without_capability_passes_decision_through() -> None:
    """No local_gate capability → passthrough carry unchanged."""
    executor = ThinkLocalGateExecutor()
    decision_in = _decision("dec_in")
    result = await executor.execute(_ctx({}, decision=decision_in), PhaseInput(artifact=None))
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)
    assert result.payload.decision is decision_in
