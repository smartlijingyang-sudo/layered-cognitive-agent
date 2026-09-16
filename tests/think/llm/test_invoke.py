"""Tests for phase.think.llm.invoke plugin (PR-B typed-port split).

Verifies the typed ``llm.invoke`` node owns only the LLM adapter call.
Drives the adapter via a mock (passed via the whitelisted runtime
carrier, like every other think subgraph node) and asserts that:

1. the node forwards ``LLMResponse`` + ``TokenUsage`` to the typed ports
2. the node never touches the journal — there is no writer in scope
3. the node forwards the model-visible identity (``state`` / ``turn`` /
   ``step`` / ``reasoner_prompt``) to ``adapter.stream`` — the fact that
   opens a journal step (regression guard, see PR-A ``test_dispatch_llm``)
4. the typed-port inputs are required and the node raises ``TypeError``
   when missing
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEvent,
    TokenUsage,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.nodes.think.llm.invoke import LlmInvokeExecutor


class _RuntimeCarrier(dict):
    """Dict + attribute proxy — the kernel runtime carrier shape."""

    def __getattr__(self, name: str) -> object:
        return self.get(name)


def _state(step: int = 3, turn: int = 7) -> AgentState:
    """AgentState with ``step`` and ``extra['current_turn']`` set."""
    state = AgentState(trace_id="trace-llm-invoke", task="", budget=Budget())
    state.step = step
    state.extra["current_turn"] = turn
    return state


def _ctx(state: AgentState, adapter: Any | None = None) -> NodeContext:
    runtime = _RuntimeCarrier(state=state)
    if adapter is not None:
        runtime["adapter"] = adapter
    return NodeContext(runtime=runtime, budget={}, metadata={})


class _FakeAdapter:
    """Minimal ``LLMAdapter`` stub capturing the call args."""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamEvent]:
        self.calls.append({"prompt": prompt, **kwargs})
        yield LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=self._response,
        )


def _request(*messages: str, system: str | None = "system") -> ModelVisibleRequest:
    return ModelVisibleRequest(
        messages=[{"role": "user", "content": m} for m in messages],
        system=system,
        tools=(),
    )


@pytest.mark.asyncio
async def test_invoke_returns_response_and_usage_on_completed_event() -> None:
    """``adapter.stream`` COMPLETED event ⇒ typed ports receive the response + usage."""
    executor = LlmInvokeExecutor()
    usage = TokenUsage(prompt_tokens=12, completion_tokens=34)
    response = LLMResponse(text="hello world", model="gpt-x", usage=usage)
    adapter = _FakeAdapter(response=response)

    output = await executor.node_execute(
        _ctx(_state(), adapter=adapter),
        NodeInput(port_values={"model_visible_request": _request("hi")}),
    )

    assert output.port_values["llm_response"] is response
    assert output.port_values["usage"] is usage


@pytest.mark.asyncio
async def test_invoke_forwards_model_visible_identity_to_stream() -> None:
    """PR-B regression guard: invoke forwards ``state``/``turn``/``step``/
    ``reasoner_prompt`` to ``adapter.stream`` via the runtime carrier."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)
    state = _state(step=3, turn=7)

    await executor.node_execute(
        _ctx(state, adapter=adapter),
        NodeInput(port_values={"model_visible_request": _request("hi", system="sys")}),
    )

    call = adapter.calls[0]
    assert call["state"] is state
    assert call["turn"] == 7
    assert call["step"] == 3
    assert call["reasoner_prompt"] is not None
    assert call["reasoner_prompt"].system_prompt_text == "sys"
    assert "session" not in call


@pytest.mark.asyncio
async def test_invoke_does_not_write_journal() -> None:
    """PR-B invariant: ``invoke`` owns only the adapter call."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)

    await executor.node_execute(
        _ctx(_state(step=1, turn=2), adapter=adapter),
        NodeInput(port_values={"model_visible_request": _request("hi")}),
    )

    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["prompt"] == "hi"
    assert call["system"] == "system"
    assert call["history"] == []


@pytest.mark.asyncio
async def test_invoke_unpacks_history_from_request_messages() -> None:
    """``messages[-1]`` → prompt; ``messages[:-1]`` → history."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)

    request = ModelVisibleRequest(
        messages=[
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "earlier reply"},
            {"role": "user", "content": "latest"},
        ],
        system="sys",
    )

    await executor.node_execute(
        _ctx(_state(), adapter=adapter),
        NodeInput(port_values={"model_visible_request": request}),
    )

    call = adapter.calls[0]
    assert call["prompt"] == "latest"
    assert call["history"] == [
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "earlier reply"},
    ]


@pytest.mark.asyncio
async def test_invoke_returns_default_usage_when_response_has_none() -> None:
    """``response.usage is None`` ⇒ typed port receives an empty ``TokenUsage``."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="no-usage", usage=None)
    adapter = _FakeAdapter(response=response)

    output = await executor.node_execute(
        _ctx(_state(), adapter=adapter),
        NodeInput(port_values={"model_visible_request": _request("hi")}),
    )

    usage = output.port_values["usage"]
    assert isinstance(usage, TokenUsage)
    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None


@pytest.mark.asyncio
async def test_invoke_missing_model_visible_request_raises() -> None:
    """``model_visible_request`` is a typed-only port; missing ⇒ TypeError."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)
    with pytest.raises(TypeError, match="model_visible_request"):
        await executor.node_execute(
            _ctx(_state(), adapter=adapter),
            NodeInput(port_values={}),
        )


@pytest.mark.asyncio
async def test_invoke_missing_adapter_raises() -> None:
    """``adapter`` not on the runtime carrier ⇒ TypeError."""
    executor = LlmInvokeExecutor()
    with pytest.raises(TypeError, match="adapter"):
        await executor.node_execute(
            _ctx(_state()),  # no adapter
            NodeInput(port_values={"model_visible_request": _request("hi")}),
        )


@pytest.mark.asyncio
async def test_invoke_no_state_in_runtime_raises() -> None:
    """No ``state`` on the runtime carrier ⇒ TypeError (fail-loud)."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)
    with pytest.raises(TypeError, match="state"):
        await executor.node_execute(
            NodeContext(runtime={}, budget={}, metadata={}),
            NodeInput(port_values={"model_visible_request": _request("hi")}),
        )


@pytest.mark.asyncio
async def test_invoke_is_idempotent() -> None:
    """Same inputs ⇒ same output across repeated calls (C9)."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)
    state = _state()
    port_values = {"model_visible_request": _request("hi")}

    out_a = await executor.node_execute(
        _ctx(state, adapter=adapter), NodeInput(port_values=port_values)
    )
    out_b = await executor.node_execute(
        _ctx(state, adapter=adapter), NodeInput(port_values=port_values)
    )

    assert out_a.port_values["llm_response"] == out_b.port_values["llm_response"]
    assert out_a.port_values["usage"] == out_b.port_values["usage"]
