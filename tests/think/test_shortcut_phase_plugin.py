"""Tests for phase.think.shortcut plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
)
from lca.plugins.think.shortcut.plugin import ThinkShortcutExecutor


@dataclass
class _NoopShortcut:
    async def try_shortcut(self, state: AgentState) -> Decision | None:
        return None


@dataclass
class _HitShortcut:
    out: Decision

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        return self.out


@dataclass
class _StubPhaseContext:
    """Minimal duck-typed stand-in for the PhaseContext Protocol."""

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


def _ctx(caps: dict[str, Any]) -> _StubPhaseContext:
    return _StubPhaseContext(
        plan_ref="p",
        node_ref="think.shortcut",
        state=AgentState(trace_id="t", task="x", budget=Budget()),
        journal=None,
        budget=None,
        artifacts={},
        capabilities=caps,
        decision=None,
        observation=None,
        reflection=None,
        checkpoint_reason=None,
    )


@pytest.mark.asyncio
async def test_shortcut_hit_returns_decision_result() -> None:
    executor = ThinkShortcutExecutor()
    decision = Decision(
        decision_id="dec_x",
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )
    result = await executor.execute(
        _ctx({"phase.think.shortcut": _HitShortcut(out=decision)}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "decision"
    assert isinstance(result.payload, Decision)


@pytest.mark.asyncio
async def test_shortcut_miss_returns_stage_result() -> None:
    executor = ThinkShortcutExecutor()
    result = await executor.execute(
        _ctx({"phase.think.shortcut": _NoopShortcut()}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)


@pytest.mark.asyncio
async def test_shortcut_missing_capability_returns_stage() -> None:
    executor = ThinkShortcutExecutor()
    result = await executor.execute(_ctx({}), PhaseInput(artifact=None))
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)
