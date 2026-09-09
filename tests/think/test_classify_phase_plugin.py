"""Tests for phase.think.classify plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
)
from lca.plugins.think.classify.plugin import ThinkClassifyExecutor


def _decision(decision_id: str = "dec_x") -> Decision:
    return Decision(  # type: ignore[call-arg]
        decision_id=decision_id,
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )


@dataclass
class _Classifier:
    out: Decision

    def classify(self, response: LLMResponse) -> Decision:
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


def _ctx(caps: dict[str, Any], response: LLMResponse | None = None) -> _StubPhaseContext:
    artifacts: dict[str, Any] = {}
    if response is not None:
        artifacts[CARRY_KEY] = ThinkSubgraphCarry(
            state=AgentState(trace_id="t", task="x", budget=Budget()),
            response=response,
        )
    return _StubPhaseContext(
        plan_ref="p",
        node_ref="think.classify",
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
async def test_classify_attaches_decision() -> None:
    executor = ThinkClassifyExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.execute(
        _ctx({"phase.think.classify": _Classifier(out=_decision("dec_a"))}, response=response),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)
    assert result.payload.decision.decision_id == "dec_a"


@pytest.mark.asyncio
async def test_classify_without_response_falls_back() -> None:
    executor = ThinkClassifyExecutor()
    result = await executor.execute(
        _ctx({"phase.think.classify": _Classifier(out=_decision())}, response=None),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    assert result.payload.decision is None


@pytest.mark.asyncio
async def test_classify_missing_capability_falls_back() -> None:
    executor = ThinkClassifyExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.execute(_ctx({}, response=response), PhaseInput(artifact=None))
    assert result.result_kind == "think_stage"
    assert result.payload.decision is None
