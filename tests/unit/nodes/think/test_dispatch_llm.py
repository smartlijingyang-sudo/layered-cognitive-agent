"""Unit tests for the ``think.llm.dispatch`` node (:class:`LlmCallExecutor`).

Regression target: after the typed-boundary split of
``think.reason.complete``, the executor was calling
``adapter.complete(prompt, system=..., history=..., tools=...)`` without
forwarding ``state`` / ``turn`` / ``step`` / ``session``. The
``TelemetryLLMAdapter`` consumes those kwargs to route
``llm.call.start/end`` through ``publish_ep_bound``; without them the
session/state pair is unbound and the events are dropped (silent journal
emptiness, run-replay lost the LLM round-trip).
"""

from __future__ import annotations

from dataclasses import dataclass
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
    """Async ``LLMAdapter`` stand-in that captures kwargs verbatim."""

    response: LLMResponse

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        # Capture the call site the test wants to assert against.
        self.last_prompt = prompt
        self.last_kwargs = kwargs
        return self.response

    async def stream(self, prompt: str, **kwargs: Any):  # pragma: no cover - stub
        if False:
            yield None


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


async def test_node_execute_forwards_state_turn_step_session_to_adapter() -> None:
    """``state`` / ``turn`` / ``step`` / ``session`` kwargs reach ``adapter.complete``.

    The ``TelemetryLLMAdapter`` is the sole emitter of
    ``llm.call.start`` / ``llm.call.end`` and only routes them through
    ``publish_ep_bound`` when both ``state`` and ``session`` are present;
    ``turn`` / ``step`` are forwarded into ``model.failed.v1`` payloads.
    """
    executor = LlmCallExecutor()
    state = _state(step=3, turn=7)
    writer = _FakeWriter()
    session = object()
    adapter = _RecordingAdapter(response=_response())
    runtime = {"adapter": adapter, "session": session}

    await executor.node_execute(
        context=_node_context(runtime=runtime),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": writer,
                "model_visible_request": _request(),
            }
        ),
    )

    assert adapter.last_kwargs.get("state") is state
    assert adapter.last_kwargs.get("turn") == 7
    assert adapter.last_kwargs.get("step") == 3
    assert adapter.last_kwargs.get("session") is session


async def test_node_execute_uses_state_step_when_turn_slot_missing() -> None:
    """``state.extra['current_turn']`` unset → ``turn`` defaults to ``0`` (not ``step``)."""
    executor = LlmCallExecutor()
    state = AgentState(trace_id="t", task="", budget=Budget())
    state.step = 11
    # No state.extra["current_turn"] set; the canonical source is unset → 0.
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={"adapter": adapter}),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
            }
        ),
    )

    assert adapter.last_kwargs.get("turn") == 0
    assert adapter.last_kwargs.get("step") == 11


async def test_node_execute_falls_back_to_module_level_publish_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``runtime.session`` ⇒ ``session`` kwarg sourced from module binding.

    Priority per task brief: ``context.runtime.session`` first,
    ``resolve_session_reader()`` second. This test pins the second leg
    so a future refactor cannot silently drop the module-level fallback.
    The module reader is patched to a sentinel rather than building a
    full Session — the test only cares that the executor reads from
    the binding when ``runtime.session`` is absent.
    """
    from lca.nodes.think.dispatch import llm as dispatch_module

    module_session = object()
    monkeypatch.setattr(dispatch_module, "resolve_session_reader", lambda: module_session)

    executor = LlmCallExecutor()
    state = _state(step=1, turn=2)
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={"adapter": adapter}),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
            }
        ),
    )

    assert adapter.last_kwargs.get("session") is module_session


async def test_node_execute_runtime_session_wins_over_module_level_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``runtime.session`` is preferred over the module-level reader.

    Pins the priority order so a future refactor cannot silently flip it.
    """
    from lca.nodes.think.dispatch import llm as dispatch_module

    runtime_session = object()
    module_session = object()
    monkeypatch.setattr(dispatch_module, "resolve_session_reader", lambda: module_session)

    executor = LlmCallExecutor()
    state = _state(step=1, turn=1)
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={"adapter": adapter, "session": runtime_session}),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
            }
        ),
    )

    assert adapter.last_kwargs.get("session") is runtime_session


async def test_node_execute_missing_state_raises_type_error() -> None:
    """No ``state`` port → the executor fails loud (no silent default).

    Same fail-loud posture as ``_resolve_port``: a missing required port
    is a contract violation, not a degraded path.
    """
    executor = LlmCallExecutor()
    adapter = _RecordingAdapter(response=_response())

    with pytest.raises(TypeError, match="'state' port must be"):
        await executor.node_execute(
            context=_node_context(runtime={"adapter": adapter}),
            input=NodeInput(
                port_values={
                    "writer": _FakeWriter(),
                    "model_visible_request": _request(),
                }
            ),
        )


async def test_node_execute_emits_step_tool_call_record_per_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each LLM tool_call → one ``record_step_tool_call`` call.

    The journal fold (``journal_fold.py:642``) consumes the spine EP
    ``step.tool_call.record``, which ``record_step_tool_call`` publishes
    via ``publish_ep_bound``. Per ``NativeToolCall`` in the response:
    ``tool_name`` / ``invocation_id`` (= ``tc.call_id``) / ``arguments``
    are forwarded verbatim, plus the resolved ``state`` and ``session``
    so the unbound-session silent-drop path can't recur.
    """
    from lca.nodes.think.dispatch import llm as dispatch_module

    calls: list[dict[str, Any]] = []

    def spy(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(dispatch_module, "record_step_tool_call", spy)

    executor = LlmCallExecutor()
    state = _state(step=4, turn=9)
    session = object()
    adapter = _RecordingAdapter(
        response=_response_with_tool_calls(
            NativeToolCall(
                call_id="call-1",
                name="echo",
                arguments={"msg": "hello"},
            ),
            NativeToolCall(
                call_id="call-2",
                name="writeFile",
                arguments={"path": "/var/data/x", "content": "abc"},
            ),
        )
    )
    runtime = {"adapter": adapter, "session": session}

    await executor.node_execute(
        context=_node_context(runtime=runtime),
        input=NodeInput(
            port_values={
                "state": state,
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
            }
        ),
    )

    assert len(calls) == 2
    first, second = calls

    assert first["tool_name"] == "echo"
    assert first["invocation_id"] == "call-1"
    assert first["arguments"] == {"msg": "hello"}
    assert first["state"] is state
    assert first["session"] is session

    assert second["tool_name"] == "writeFile"
    assert second["invocation_id"] == "call-2"
    assert second["arguments"] == {"path": "/var/data/x", "content": "abc"}
    assert second["state"] is state
    assert second["session"] is session


async def test_node_execute_no_tool_calls_skips_step_tool_call_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty ``response.tool_calls`` → ``record_step_tool_call`` not called.

    A response with only text (no native tool calls) is the common
    ``respond`` decision path; the empty loop must not emit a phantom
    ``step.tool_call.record`` spine fact.
    """
    from lca.nodes.think.dispatch import llm as dispatch_module

    calls: list[dict[str, Any]] = []

    def spy(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(dispatch_module, "record_step_tool_call", spy)

    executor = LlmCallExecutor()
    adapter = _RecordingAdapter(response=_response())

    await executor.node_execute(
        context=_node_context(runtime={"adapter": adapter}),
        input=NodeInput(
            port_values={
                "state": _state(),
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
            }
        ),
    )

    assert calls == []


async def test_node_execute_step_tool_call_arguments_summary_truncates_long_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-empty arguments → ``arguments_summary`` is derived and ≤ 200 chars.

    Pins the contract that ``summarize_args`` (canonical body-side
    helper) is the source of the summary: keys joined with ``=``, values
    repr'd and truncated, total length bounded by ~200 chars.
    """
    from lca.nodes.think.dispatch import llm as dispatch_module

    calls: list[dict[str, Any]] = []

    def spy(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(dispatch_module, "record_step_tool_call", spy)

    long_value = "x" * 500
    executor = LlmCallExecutor()
    adapter = _RecordingAdapter(
        response=_response_with_tool_calls(
            NativeToolCall(
                call_id="call-1",
                name="echo",
                arguments={"key": long_value},
            ),
        )
    )

    await executor.node_execute(
        context=_node_context(runtime={"adapter": adapter}),
        input=NodeInput(
            port_values={
                "state": _state(),
                "writer": _FakeWriter(),
                "model_visible_request": _request(),
            }
        ),
    )

    assert len(calls) == 1
    summary = calls[0]["arguments_summary"]
    assert summary  # non-empty for a non-empty dict
    assert len(summary) <= 201  # 200 + the trailing ellipsis char
