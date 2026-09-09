"""Tests for phase.think.reason plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.think_carry import ThinkSubgraphCarry
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
)
from lca.plugins.think.reason.plugin import ThinkReasonExecutor


@dataclass
class _Reasoner:
    response: LLMResponse

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:
        return self.response


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


def _ctx(caps: dict[str, Any]) -> _StubPhaseContext:
    return _StubPhaseContext(
        plan_ref="p",
        node_ref="think.reason",
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
async def test_reason_attaches_response_to_carry() -> None:
    executor = ThinkReasonExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.execute(
        _ctx({"phase.think.reason": _Reasoner(response=response)}),
        PhaseInput(artifact=None),
    )
    assert result.result_kind == "think_stage"
    carry = result.payload
    assert isinstance(carry, ThinkSubgraphCarry)
    assert carry.response is response


@pytest.mark.asyncio
async def test_reason_missing_capability_falls_back() -> None:
    executor = ThinkReasonExecutor()
    result = await executor.execute(_ctx({}), PhaseInput(artifact=None))
    assert result.result_kind == "think_stage"
    assert isinstance(result.payload, ThinkSubgraphCarry)
    assert result.payload.response is None


@pytest.mark.asyncio
async def test_reason_preserves_prior_carry_decision() -> None:
    """If a previous step populated ``decision`` on the carry, reason does not erase it."""
    from lca.contracts.models.core.execution.decision import Decision
    from lca.contracts.models.core.execution.think_carry import CARRY_KEY

    executor = ThinkReasonExecutor()
    prior = Decision(  # type: ignore[call-arg]
        decision_id="dec_prior",
        action_type="respond",
        rationale="r",
        confidence=1.0,
    )
    response = LLMResponse(text="new", tool_calls=())
    state = AgentState(trace_id="t", task="x", budget=Budget())
    carry = ThinkSubgraphCarry(state=state, decision=prior)
    ctx = _ctx({"phase.think.reason": _Reasoner(response=response)})
    ctx.artifacts[CARRY_KEY] = carry

    result = await executor.execute(ctx, PhaseInput(artifact=None))

    assert result.result_kind == "think_stage"
    assert result.payload.decision is prior
    assert result.payload.response is response
