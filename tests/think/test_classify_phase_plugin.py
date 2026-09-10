"""Tests for phase.think.classify plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.plugins.think.classify import ThinkClassifyExecutor


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
class _StubRuntime:
    state: Any
    decision_classifier: Any


def _ctx(caps: dict[str, Any], response: LLMResponse | None = None) -> NodeContext:
    runtime = _StubRuntime(
        state=None,
        decision_classifier=caps.get("phase.think.classify"),
    )
    port_values: dict[str, Any] = {}
    if response is not None:
        port_values["response"] = response
    return NodeContext(runtime=runtime, budget={}, metadata={})


@pytest.mark.asyncio
async def test_classify_attaches_decision_port() -> None:
    executor = ThinkClassifyExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.node_execute(
        _ctx({"phase.think.classify": _Classifier(out=_decision("dec_a"))}, response=response),
        NodeInput(port_values={"response": response}),
    )
    assert result.port_values.get("decision").decision_id == "dec_a"


@pytest.mark.asyncio
async def test_classify_without_response_returns_empty_ports() -> None:
    executor = ThinkClassifyExecutor()
    result = await executor.node_execute(
        _ctx({"phase.think.classify": _Classifier(out=_decision())}, response=None),
        NodeInput(port_values={}),
    )
    assert result.port_values == {}


@pytest.mark.asyncio
async def test_classify_missing_capability_returns_empty_ports() -> None:
    executor = ThinkClassifyExecutor()
    response = LLMResponse(text="hi", tool_calls=())
    result = await executor.node_execute(
        _ctx({}, response=response),
        NodeInput(port_values={"response": response}),
    )
    assert result.port_values == {}