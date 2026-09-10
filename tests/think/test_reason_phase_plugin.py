"""Tests for phase.think.reason plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.plugins.think.reason.entry import ThinkReasonExecutor


@dataclass
class _Reasoner:
    response: LLMResponse

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:
        return self.response


@dataclass
class _StubRuntime:
    state: AgentState | None
    reasoner: Any


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        reasoner=caps.get("phase.think.reason"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


@pytest.mark.asyncio
async def test_reason_attaches_response_port() -> None:
    executor = ThinkReasonExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.node_execute(
        _ctx({"phase.think.reason": _Reasoner(response=response)}),
        NodeInput(port_values={}),
    )
    assert result.port_values.get("response") is response


@pytest.mark.asyncio
async def test_reason_missing_capability_returns_empty_ports() -> None:
    executor = ThinkReasonExecutor()
    result = await executor.node_execute(_ctx({}), NodeInput(port_values={}))
    assert result.port_values == {}
