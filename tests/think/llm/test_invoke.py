"""Tests for phase.think.llm.invoke plugin (PR-B typed-port split).

Verifies the typed ``llm.invoke`` node owns only the LLM adapter call.
Drives the adapter via a mock and asserts that:

1. the node forwards ``LLMResponse`` + ``TokenUsage`` to the typed ports
2. the node never touches the journal — there is no writer in scope
3. the typed-port inputs are required and the node raises ``TypeError``
   when missing (no silent fallback to ``context.runtime``)
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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.nodes.think.llm.invoke import LlmInvokeExecutor


class _FakeAdapter:
    """Minimal ``LLMAdapter`` stub capturing the call args.

    The invoke node only depends on ``stream(prompt, system, history,
    tools, **kwargs)``; the fake exposes a single ``COMPLETED`` event
    carrying the supplied response.
    """

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


def _ctx() -> NodeContext:
    """Empty context — invoke is pure typed-port, never reads runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


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
        _ctx(),
        NodeInput(
            port_values={
                "model_visible_request": _request("hi"),
                "adapter": adapter,
            }
        ),
    )

    assert output.port_values["llm_response"] is response
    assert output.port_values["usage"] is usage


@pytest.mark.asyncio
async def test_invoke_does_not_write_journal() -> None:
    """PR-B invariant: ``invoke`` owns only the adapter call.

    The journal path lives in the sibling ``think.llm.persist`` node.
    The invoke executor must not call any writer / append method, so
    the fake adapter contract has no journal surface and the test
    asserts no extra attributes were touched.
    """
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)

    await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "model_visible_request": _request("hi"),
                "adapter": adapter,
            }
        ),
    )

    # Adapter call capture is the only observable side effect.
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["prompt"] == "hi"
    assert call["system"] == "system"
    # History is the messages before the last one (empty in this case).
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
        _ctx(),
        NodeInput(
            port_values={
                "model_visible_request": request,
                "adapter": adapter,
            }
        ),
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
        _ctx(),
        NodeInput(
            port_values={
                "model_visible_request": _request("hi"),
                "adapter": adapter,
            }
        ),
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
    with pytest.raises(TypeError, match="model_visible_request"):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={"adapter": _FakeAdapter(response=response)}
            ),
        )


@pytest.mark.asyncio
async def test_invoke_missing_adapter_raises() -> None:
    """``adapter`` is a typed-only port; missing ⇒ TypeError."""
    executor = LlmInvokeExecutor()
    with pytest.raises(TypeError, match="adapter"):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"model_visible_request": _request("hi")}),
        )


@pytest.mark.asyncio
async def test_invoke_is_idempotent() -> None:
    """Same inputs ⇒ same output across repeated calls (C9)."""
    executor = LlmInvokeExecutor()
    response = LLMResponse(text="ok", usage=TokenUsage())
    adapter = _FakeAdapter(response=response)
    port_values = {
        "model_visible_request": _request("hi"),
        "adapter": adapter,
    }

    out_a = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))
    out_b = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))

    assert out_a.port_values["llm_response"] == out_b.port_values["llm_response"]
    assert out_a.port_values["usage"] == out_b.port_values["usage"]
