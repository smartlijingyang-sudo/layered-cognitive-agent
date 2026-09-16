"""Tests for phase.think.llm.persist plugin (PR-B typed-port split).

Verifies the typed ``llm.persist`` node owns only the journal-write
side-effect of the LLM turn. Drives a ``RunSessionWriterProtocol``
mock and asserts that:

1. the assistant row + one ``log/tool_call`` row per call are appended
2. the node never calls the LLM adapter (no adapter port in scope)
3. the typed-port inputs are required
4. the typed ``journaled`` boolean port reflects the write
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


def _state(step: int = 1) -> AgentState:
    """``AgentState`` carrying ``step`` (persist derives turn/step from it)."""
    state = AgentState(trace_id="trace-llm-persist", task="", budget=Budget())
    state.step = step
    return state


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


def _ctx() -> NodeContext:
    """Persist is typed-only — never reads runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


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
        _ctx(),
        NodeInput(
            port_values={
                "state": _state(3),
                "llm_response": response,
                "writer": writer,
            }
        ),
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
            NativeToolCall(
                call_id="call-1",
                name="search",
                arguments={"q": "lc"},
            ),
            NativeToolCall(
                call_id="call-2",
                name="write",
                arguments={"path": "out/x"},
            ),
        ),
    )

    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": _state(7),
                "llm_response": response,
                "writer": writer,
            }
        ),
    )

    assert output.port_values == {"journaled": True}
    # 1 assistant row + 2 tool_call rows
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
    # Assistant row carries tool_calls array so the projection sees both.
    assistant_row = writer.calls[0]
    assert assistant_row.kwargs["tool_calls"] is not None
    assert len(assistant_row.kwargs["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_persist_does_not_call_adapter() -> None:
    """PR-B invariant: ``persist`` owns only the writer — no adapter in scope.

    The node declares ``adapter`` outside its ``declared_inputs`` tuple
    and never imports ``LLMAdapter``. A dummy adapter-like object in
    the test fixture must remain untouched.
    """
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    response = _response()

    # A sentinel "adapter" placed in port_values but NOT declared by
    # the node. The node must not read it (the typed-port contract
    # only consumes declared inputs).
    sentinel_called = {"value": False}

    class _AdapterSentinel:
        async def stream(self, *args: Any, **kwargs: Any) -> Any:
            sentinel_called["value"] = True
            yield None  # pragma: no cover

    await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": _state(1),
                "llm_response": response,
                "writer": writer,
                "adapter": _AdapterSentinel(),
            }
        ),
    )

    assert sentinel_called["value"] is False
    assert writer.append_calls == 1


@pytest.mark.asyncio
async def test_persist_missing_writer_raises() -> None:
    """``writer`` is a typed-only port; missing ⇒ TypeError."""
    executor = LlmPersistExecutor()
    with pytest.raises(TypeError, match="writer"):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "state": _state(1),
                    "llm_response": _response(),
                }
            ),
        )


@pytest.mark.asyncio
async def test_persist_missing_response_raises() -> None:
    """``llm_response`` is a typed-only port; missing ⇒ TypeError."""
    executor = LlmPersistExecutor()
    with pytest.raises(TypeError, match="llm_response"):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "state": _state(1),
                    "writer": _FakeWriter(),
                }
            ),
        )


@pytest.mark.asyncio
async def test_persist_missing_state_raises() -> None:
    """``state`` is a required carrier; missing (typed port + runtime) ⇒ TypeError."""
    executor = LlmPersistExecutor()
    with pytest.raises(TypeError, match="state"):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "llm_response": _response(),
                    "writer": _FakeWriter(),
                }
            ),
        )


@pytest.mark.asyncio
async def test_persist_resolves_state_from_runtime_carrier() -> None:
    """``state`` absent from typed ports ⇒ resolved via whitelisted runtime carrier."""
    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    ctx = NodeContext(runtime={"state": _state(4)}, budget={}, metadata={})
    await executor.node_execute(
        ctx,
        NodeInput(
            port_values={
                "llm_response": _response(),
                "writer": writer,
            }
        ),
    )
    assert writer.calls[0].kwargs["turn"] == 4
    assert writer.calls[0].kwargs["step"] == 4


@pytest.mark.asyncio
async def test_persist_is_idempotent() -> None:
    """Same inputs ⇒ identical writer calls (C9)."""
    executor = LlmPersistExecutor()
    response = _response(text="ok")
    port_values = {
        "state": _state(2),
        "llm_response": response,
        "writer": _FakeWriter(),
    }

    out_a = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))
    out_b = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))

    assert out_a.port_values == out_b.port_values == {"journaled": True}


@pytest.mark.asyncio
async def test_persist_does_not_commit_step_tool_call_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-owner guard (migrated from pre-split ``test_dispatch_llm``).

    ``step.tool_call.record`` has exactly one producer: the body executor
    that starts the invocation. The persist node writes the conversation
    rows only — a second emit here double-counts
    ``metrics_projection.tool_call_count``.
    """
    import lca.loop.commit.tool_journal as tool_journal

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(tool_journal, "record_step_tool_call", lambda **kw: calls.append(kw))

    executor = LlmPersistExecutor()
    writer = _FakeWriter()
    response = _response(
        tool_calls=(NativeToolCall(call_id="call-1", name="echo", arguments={"msg": "x"}),)
    )
    await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={"state": _state(4), "llm_response": response, "writer": writer}
        ),
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
