"""Tests for phase.think.llm.persist plugin (PR-B typed-port split).

Verifies the typed ``llm.persist`` node owns only the journal-write
side-effect of the LLM turn. Drives a ``RunSessionWriterProtocol``
mock (passed via the whitelisted runtime carrier, like every other
think subgraph node) and asserts that:

1. the assistant row + one ``log/tool_call`` row per call are appended
2. the node never calls the LLM adapter (no adapter port in scope)
3. the typed-port inputs are required
4. the typed ``journaled`` boolean port reflects the write
5. ``state.step`` drives the writer rows via the runtime carrier
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    NativeToolCall,
    TokenUsage,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.think.llm.persist import LlmPersistExecutor


class _RuntimeCarrier(dict):
    def __getattr__(self, name: str) -> object:
        return self.get(name)


def _state(step: int = 1) -> AgentState:
    state = AgentState(trace_id="trace-llm-persist", task="", budget=Budget())
    state.step = step
    return state


def _ctx(state: AgentState, writer: Any | None = None) -> NodeContext:
    runtime = _RuntimeCarrier(state=state)
    if writer is not None:
        runtime["writer"] = writer
    return NodeContext(runtime=runtime, budget={}, metadata={})


@dataclass
class _CallRecord:
    """Captured append call."""

    method: str
    kwargs: dict[str, Any]


@dataclass
class _FakeWriter:
    """Minimal ``RunSessionWriterProtocol`` capturing append calls."""

    calls: list[_CallRecord] = field(default_factory=list)
    append_calls: int = 0
    tool_call_calls: int = 0

    def append_assistant_message(self, **kwargs: Any) -> object:
        self.append_calls += 1
        self.calls.append(_CallRecord(method="append_assistant_message", kwargs=kwargs))
        return f"ref-assistant-{self.append_calls}"

    def append_tool_call(self, **kwargs: Any) -> object:
        self.tool_call_calls += 1
        self.calls.append(_CallRecord(method="append_tool_call", kwargs=kwargs))
        return f"ref-tool-{self.tool_call_calls}"


def _response(
    *,
    text: str = "hello",
    tool_calls: tuple[NativeToolCall, ...] = (),
    usage: TokenUsage | None = None,
) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=list(tool_calls), usage=usage)


@pytest.mark.asyncio
async def test_persist_writes_assistant_message_only() -> None:
    """No tool calls ⇒ one ``append_assistant_message`` call, no tool rows."""
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    response = _response(text="hello", usage=TokenUsage(prompt_tokens=1, completion_tokens=2))

    output = await executor.node_execute(
        _ctx(_state(step=3), writer=writer),
        NodeInput(port_values={"llm_response": response}),
    )

    assert output.port_values == {"journaled": True}
    assert writer.append_calls == 1
    assert writer.tool_call_calls == 0
    call = writer.calls[0]
    assert call.method == "append_assistant_message"
    assert call.kwargs["turn"] == 3
    assert call.kwargs["step"] == 3
    assert call.kwargs["role"] == "assistant"
    assert call.kwargs["content"] == "hello"
    assert call.kwargs["tool_calls"] is None
    assert call.kwargs["usage"] == TokenUsage(prompt_tokens=1, completion_tokens=2)


@pytest.mark.asyncio
async def test_persist_writes_one_tool_call_row_per_call() -> None:
    """Each ``NativeToolCall`` ⇒ one ``append_tool_call`` row."""
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    response = _response(
        text="",
        tool_calls=(
            NativeToolCall(call_id="call-1", name="search", arguments={"q": "lc"}),
            NativeToolCall(call_id="call-2", name="write", arguments={"path": "out/x"}),
        ),
    )

    output = await executor.node_execute(
        _ctx(_state(step=7), writer=writer),
        NodeInput(port_values={"llm_response": response}),
    )

    assert output.port_values == {"journaled": True}
    assert writer.append_calls == 1
    assert writer.tool_call_calls == 2
    methods = [c.method for c in writer.calls]
    assert methods == [
        "append_assistant_message",
        "append_tool_call",
        "append_tool_call",
    ]
    tool_rows = [c for c in writer.calls if c.method == "append_tool_call"]
    assert tool_rows[0].kwargs["call_id"] == "call-1"
    assert tool_rows[0].kwargs["name"] == "search"
    assert tool_rows[1].kwargs["call_id"] == "call-2"
    assert tool_rows[1].kwargs["name"] == "write"
    assistant_row = writer.calls[0]
    assert assistant_row.kwargs["tool_calls"] is not None
    assert len(assistant_row.kwargs["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_persist_does_not_call_adapter() -> None:
    """PR-B invariant: ``persist`` owns only the writer — no adapter in scope."""
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    response = _response()

    sentinel_called = {"value": False}

    class _AdapterSentinel:
        async def stream(self, *args: Any, **kwargs: Any) -> Any:
            sentinel_called["value"] = True
            yield None  # pragma: no cover

    await executor.node_execute(
        _ctx(_state(step=1), writer=writer),
        NodeInput(
            port_values={
                "llm_response": response,
                "adapter": _AdapterSentinel(),
            }
        ),
    )

    assert sentinel_called["value"] is False
    assert writer.append_calls == 1


@pytest.mark.asyncio
async def test_persist_missing_writer_raises() -> None:
    """``writer`` not on the runtime carrier ⇒ TypeError (fail-loud)."""
    executor = LlmPersistExecutor()
    with pytest.raises(TypeError, match="writer"):
        await executor.node_execute(
            _ctx(_state(step=1)),  # no writer
            NodeInput(port_values={"llm_response": _response()}),
        )


@pytest.mark.asyncio
async def test_persist_missing_response_raises() -> None:
    """``llm_response`` is a typed-only port; missing ⇒ TypeError."""
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    with pytest.raises(TypeError, match="llm_response"):
        await executor.node_execute(
            _ctx(_state(step=1), writer=writer),
            NodeInput(port_values={}),
        )


@pytest.mark.asyncio
async def test_persist_no_state_in_runtime_raises() -> None:
    """No ``state`` on the runtime carrier ⇒ TypeError (fail-loud)."""
    executor = LlmPersistExecutor()
    with pytest.raises(TypeError, match="state"):
        await executor.node_execute(
            NodeContext(runtime={}, budget={}, metadata={}),
            NodeInput(port_values={}),
        )


@pytest.mark.asyncio
async def test_persist_step_from_state_carrier() -> None:
    """``state.step`` (runtime carrier) drives the writer row turn/step."""
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    await executor.node_execute(
        _ctx(_state(step=4), writer=writer),
        NodeInput(port_values={"llm_response": _response()}),
    )
    assert writer.calls[0].kwargs["turn"] == 4
    assert writer.calls[0].kwargs["step"] == 4


@pytest.mark.asyncio
async def test_persist_does_not_commit_step_tool_call_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-owner guard: persist must not emit ``step.tool_call.record``."""
    import lca.loop.commit.tool_journal as tool_journal

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(tool_journal, "record_step_tool_call", lambda **kw: calls.append(kw))

    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    response = _response(
        tool_calls=(NativeToolCall(call_id="call-1", name="echo", arguments={"msg": "x"}),)
    )
    await executor.node_execute(
        _ctx(_state(step=4), writer=writer),
        NodeInput(port_values={"llm_response": response}),
    )

    assert calls == [], f"persist must not commit step.tool_call.record: {calls!r}"
    assert writer.tool_call_calls == 1


def test_persist_module_has_no_tool_journal_commit_reference() -> None:
    """Structural lock behind the behavioural spy above."""
    from pathlib import Path

    import lca.nodes.think.llm.persist as persist_module

    source = Path(persist_module.__file__).read_text(encoding="utf-8")
    assert "record_step_tool_call" not in source, (
        "persist re-gained a second step.tool_call.record producer; the body "
        "executor is the single owner"
    )


@pytest.mark.asyncio
async def test_persist_is_idempotent() -> None:
    """Same ``state`` + inputs ⇒ identical writer calls (C9)."""
    executor = LlmPersistExecutor()
    state = _state(step=2)
    writer = _FakeWriter()
    port_values = {"llm_response": _response(text="ok")}

    out_a = await executor.node_execute(
        _ctx(state, writer=writer), NodeInput(port_values=port_values)
    )
    out_b = await executor.node_execute(
        _ctx(state, writer=writer), NodeInput(port_values=port_values)
    )

    assert out_a.port_values == out_b.port_values == {"journaled": True}
