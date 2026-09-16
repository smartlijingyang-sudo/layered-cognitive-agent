"""Unit tests for the ``think.llm.dispatch`` node (:class:`LlmCallExecutor`).

Regression target: after the typed-boundary split of
``think.reason.complete``, the executor stopped driving the streaming
adapter boundary and dropped the ``cursor`` / ``reasoner_prompt``
identity, so ``llm.stream.token`` (reasoning channel) and
``llm.request.header`` were never produced — the journal fold opens a
step only on the header, so ``journal.steps`` went empty. It also injected
the Session *reader* as the publish writer, which appends around the run
bridge and loses the spine ledger write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEvent,
    LLMStreamEventType,
    NativeToolCall,
    TokenUsage,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.nodes.think.dispatch.llm import LlmCallExecutor

# ── Minimal stubs ────────────────────────────────────────────────


@dataclass
class _FakeWriter:
    """No-op ``RunSessionWriterProtocol`` stand-in — capture calls only."""

    def __init__(self) -> None:
        self.assistant_messages: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []

    def append_assistant_message(self, **kwargs: Any) -> Any:
        self.assistant_messages.append(kwargs)
        return None

    def append_tool_call(self, **kwargs: Any) -> Any:
        self.tool_calls.append(kwargs)
        return None


@dataclass
class _RecordingAdapter:
    """Async ``LLMAdapter`` stand-in that captures the streaming call kwargs."""

    response: LLMResponse
    last_prompt: str = ""
    last_kwargs: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.last_kwargs is None:
            self.last_kwargs = {}

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:  # pragma: no cover
        raise AssertionError("llm.call must drive the streaming boundary, not complete()")

    async def stream(self, prompt: str, **kwargs: Any):
        self.last_prompt = prompt
        self.last_kwargs = kwargs
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=self.response)


def _state(step: int = 3, turn: int = 7) -> AgentState:
    """AgentState with ``step`` and ``extra['current_turn']`` set."""
    state = AgentState(trace_id="trace-llm-dispatch", task="", budget=Budget())
    state.step = step
    state.extra["current_turn"] = turn
    return state


def _request() -> ModelVisibleRequest:
    return ModelVisibleRequest(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "earlier"},
            {"role": "user", "content": "ask"},
        ],
        system="sys",
        tools=(),
    )


def _response() -> LLMResponse:
    return LLMResponse(text="ok", model="m", usage=TokenUsage(), tool_calls=[])


def _response_with_tool_calls(*calls: NativeToolCall) -> LLMResponse:
    return LLMResponse(text="", model="m", usage=TokenUsage(), tool_calls=list(calls))


def _node_context(runtime: Any = None) -> NodeContext:
    return NodeContext(runtime=runtime, budget={}, metadata={})


# ── Tests ────────────────────────────────────────────────────────


async def test_node_execute_forwards_identity_to_streaming_boundary() -> None:
    """``state`` / ``turn`` / ``step`` / ``cursor`` / ``reasoner_prompt`` reach
    ``adapter.stream``.

    ``TelemetryLLMAdapter`` emits ``llm.call.start/end`` + ``llm.stream.token``
    from the streaming boundary, and ``ModelVisibleHookAdapter`` needs
    ``cursor`` + ``reasoner_prompt`` to publish ``llm.request.header`` — the
    only fact that opens a journal step.
    """
    executor = LlmCallExecutor()
    state = _state(step=3, turn=7)
    writer = _FakeWriter()
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={"session": object()}),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": writer,
                "model_visible_request": _request(),
                "adapter": adapter,
            }
        ),
    )

    assert adapter.last_kwargs.get("state") is state
    assert adapter.last_kwargs.get("turn") == 7
    assert adapter.last_kwargs.get("step") == 3
    assert adapter.last_kwargs.get("reasoner_prompt") is not None
    assert adapter.last_kwargs["reasoner_prompt"].system_prompt_text == "sys"


async def test_node_execute_does_not_inject_a_publish_writer() -> None:
    """The node never hands a Session to the emit seam.

    FactGateway owns writer resolution; injecting the Session *reader* appends
    behind :class:`RunEventSessionBridge`, so the fact reaches the log but not
    the spine ledger.
    """
    executor = LlmCallExecutor()
    state = _state(step=1, turn=2)
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={"session": object()}),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
                "adapter": adapter,
            }
        ),
    )

    assert "session" not in adapter.last_kwargs


async def test_node_execute_uses_state_step_when_turn_slot_missing() -> None:
    """``state.extra['current_turn']`` unset → ``turn`` defaults to ``0`` (not ``step``)."""
    executor = LlmCallExecutor()
    state = AgentState(trace_id="t", task="", budget=Budget())
    state.step = 11
    # No state.extra["current_turn"] set; the canonical source is unset → 0.
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={}),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
                "adapter": adapter,
            }
        ),
    )

    assert adapter.last_kwargs.get("turn") == 0
    assert adapter.last_kwargs.get("step") == 11


async def test_node_execute_missing_state_raises_type_error() -> None:
    """No ``state`` port → the executor fails loud (no silent default).

    Same fail-loud posture as ``_resolve_port``: a missing required port
    is a contract violation, not a degraded path.
    """
    executor = LlmCallExecutor()
    adapter = _RecordingAdapter(response=_response())

    with pytest.raises(TypeError, match="'state' port must be"):
        await executor.node_execute(
            context=_node_context(runtime={}),
            input=NodeInput(
                port_values={
                    "writer": _FakeWriter(),
                    "model_visible_request": _request(),
                    "adapter": adapter,
                }
            ),
        )


async def test_node_execute_does_not_commit_step_tool_call_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The node must not write ``step.tool_call.record`` — the body owns it.

    ``SimpleSafeExecutor.execute`` (and its pipeline twin) is the single
    producer of that spine EP per invocation. A second emit from here wrote a
    byte-identical row under the same ``invocation_id``, which
    ``metrics_projection.tool_call_count`` counted twice. Spying on the
    canonical function (not a module-local alias) catches a re-introduction
    whatever import path the node uses.
    """
    import lca.loop.commit.tool_journal as tool_journal

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(tool_journal, "record_step_tool_call", lambda **kw: calls.append(kw))

    executor = LlmCallExecutor()
    adapter = _RecordingAdapter(
        response=_response_with_tool_calls(
            NativeToolCall(call_id="call-1", name="echo", arguments={"msg": "hello"}),
            NativeToolCall(
                call_id="call-2", name="writeFile", arguments={"path": "/x", "content": "abc"}
            ),
        )
    )

    await executor.node_execute(
        context=_node_context(runtime={}),
        input=NodeInput(
            port_values={
                "state": _state(step=4, turn=9),
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
                "adapter": adapter,
            }
        ),
    )

    assert calls == [], f"llm.call must not commit step.tool_call.record: {calls!r}"


def test_node_module_has_no_tool_journal_commit_reference() -> None:
    """Structural lock behind the behavioural spy above.

    A top-level ``from lca.loop.commit.tool_journal import record_step_tool_call``
    would bind the name before a monkeypatch could take effect, so also assert
    the node source never mentions the canonical emitter.
    """
    from pathlib import Path

    import lca.nodes.think.dispatch.llm as dispatch_module

    source = Path(dispatch_module.__file__).read_text(encoding="utf-8")
    assert "record_step_tool_call" not in source, (
        "llm.call re-gained a second step.tool_call.record producer; the body "
        "executor is the single owner"
    )


async def test_node_execute_persists_declared_tool_calls_to_the_writer() -> None:
    """Declared tool calls still reach the Session writer (assistant row + tool rows).

    Dropping the spine emit must not drop the conversation facts the fold and
    the next model turn read.
    """
    executor = LlmCallExecutor()
    writer = _FakeWriter()
    adapter = _RecordingAdapter(
        response=_response_with_tool_calls(
            NativeToolCall(call_id="call-1", name="echo", arguments={"msg": "hello"}),
            NativeToolCall(call_id="call-2", name="writeFile", arguments={"path": "/x"}),
        )
    )

    await executor.node_execute(
        context=_node_context(runtime={}),
        input=NodeInput(
            port_values={
                "state": _state(step=4, turn=9),
                "writer": writer,
                "model_visible_request": _request(),
                "adapter": adapter,
            }
        ),
    )

    assert [c["call_id"] for c in writer.tool_calls] == ["call-1", "call-2"]
    assert writer.assistant_messages[0]["tool_calls"] is not None
    assert len(writer.assistant_messages[0]["tool_calls"]) == 2
