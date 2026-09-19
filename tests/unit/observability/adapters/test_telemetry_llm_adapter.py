"""Unit tests for ``TelemetryLLMAdapter`` spine EP forwarding.

Regression target: the journal-empty bug closed by Task 1.5. The
``TelemetryLLMAdapter.complete()`` / ``stream()`` were emitting
``llm.call.start`` / ``llm.call.end`` via ``publish_ep_bound`` without
forwarding the ``state`` / ``session`` kwargs that
``LlmCallExecutor`` passes. With both unbound, ``publish_ep_bound``
returns ``None`` and the events are silently dropped — so the spine
JSONL never sees the LLM round-trip and the journal fold has nothing
to project.

This test pins that the seam forwards ``state`` and ``session``
verbatim to the underlying emitter, in both ``complete()`` and
``stream()``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEvent,
    TokenUsage,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.observability.adapters import TelemetryLLMAdapter

# ── Spy / stub ──────────────────────────────────────────────────


@dataclass
class _SpySpine:
    """Records every spine EP emit call as a ``(method, kwargs)`` pair.

    Mirrors :class:`LlmSpineEmitter` enough that ``TelemetryLLMAdapter``
    treats it as the injected ``spine_emit``. Each emit returns
    ``None`` so the adapter's ``publish_ep_bound``-shaped contract is
    not violated.
    """

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def emit_llm_call_start(self, **kwargs: Any) -> None:
        self.calls.append(("emit_llm_call_start", kwargs))

    def emit_llm_call_end(self, **kwargs: Any) -> None:
        self.calls.append(("emit_llm_call_end", kwargs))

    def emit_llm_stream_token(self, **kwargs: Any) -> None:
        self.calls.append(("emit_llm_stream_token", kwargs))

    def emit_llm_stream_stall(self, **kwargs: Any) -> None:
        self.calls.append(("emit_llm_stream_stall", kwargs))


@dataclass
class _FakeInner(LLMAdapter):
    """Stub inner adapter — captures the kwargs forwarded by the decorator."""

    name: str = "fake-inner"
    fail: bool = False

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        if self.fail:
            raise RuntimeError("boom")
        return LLMResponse(
            text="done",
            model="fake-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        del prompt, kwargs
        if self.fail:
            raise RuntimeError("stream boom")
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="hi")
        response = LLMResponse(
            text="hi",
            model="fake-model",
            usage=TokenUsage(prompt_tokens=20, completion_tokens=8),
        )
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


def _state() -> AgentState:
    state = AgentState(trace_id="trace-llm-adapter", task="", budget=Budget())
    state.step = 3
    state.extra["current_turn"] = 7
    return state


# ── Tests ───────────────────────────────────────────────────────


async def test_complete_forwards_state_and_session_to_spine_emit_start() -> None:
    """``state`` / ``session`` reach ``emit_llm_call_start`` verbatim."""
    spy = _SpySpine()
    state = _state()
    session = object()
    adapter = TelemetryLLMAdapter(_FakeInner(), spine_emit=spy)

    await adapter.complete("prompt", state=state, session=session)

    starts = [c for c in spy.calls if c[0] == "emit_llm_call_start"]
    assert len(starts) == 1
    assert starts[0][1]["state"] is state
    assert starts[0][1]["session"] is session


async def test_complete_forwards_state_and_session_to_spine_emit_end() -> None:
    """``state`` / ``session`` reach ``emit_llm_call_end`` verbatim (success path)."""
    spy = _SpySpine()
    state = _state()
    session = object()
    adapter = TelemetryLLMAdapter(_FakeInner(), spine_emit=spy)

    await adapter.complete("prompt", state=state, session=session)

    ends = [c for c in spy.calls if c[0] == "emit_llm_call_end"]
    assert len(ends) == 1
    assert ends[0][1]["outcome"] == "success"
    assert ends[0][1]["state"] is state
    assert ends[0][1]["session"] is session


async def test_complete_failure_path_also_forwards_state_and_session() -> None:
    """Inner ``RuntimeError`` ⇒ ``emit_llm_call_end`` still carries ``state`` / ``session``."""
    spy = _SpySpine()
    state = _state()
    session = object()
    inner = _FakeInner()
    inner.fail = True
    adapter = TelemetryLLMAdapter(inner, spine_emit=spy)

    with pytest.raises(RuntimeError, match="boom"):
        await adapter.complete("prompt", state=state, session=session)

    ends = [c for c in spy.calls if c[0] == "emit_llm_call_end"]
    assert len(ends) == 1
    assert ends[0][1]["outcome"] == "failure"
    assert ends[0][1]["state"] is state
    assert ends[0][1]["session"] is session


async def test_complete_strips_state_and_session_from_inner_kwargs() -> None:
    """Inner adapter never sees ``state`` / ``session`` (its contract has no such fields).

    ``turn`` / ``step`` are also stripped (they're observability metadata
    consumed by the spine seam, not the inner adapter's contract).
    """
    inner = _FakeInner()
    inner.last_kwargs: dict[str, Any] | None = None

    async def _record_complete(prompt: str, **kwargs: Any) -> LLMResponse:
        inner.last_kwargs = dict(kwargs)
        return LLMResponse(text="x", model="m", usage=TokenUsage())

    inner.complete = _record_complete  # type: ignore[assignment]
    adapter = TelemetryLLMAdapter(inner, spine_emit=_SpySpine())

    state = _state()
    session = object()
    await adapter.complete(
        "prompt",
        state=state,
        session=session,
        turn=7,
        step=3,
        system="sys",
    )

    assert inner.last_kwargs is not None
    assert "state" not in inner.last_kwargs
    assert "session" not in inner.last_kwargs
    assert "turn" not in inner.last_kwargs
    assert "step" not in inner.last_kwargs
    assert inner.last_kwargs["system"] == "sys"


async def test_stream_forwards_state_and_session_to_spine_emit_start() -> None:
    """``state`` / ``session`` reach ``emit_llm_call_start`` on the stream path."""
    spy = _SpySpine()
    state = _state()
    session = object()
    adapter = TelemetryLLMAdapter(_FakeInner(), spine_emit=spy)

    _events = [e async for e in adapter.stream("prompt", state=state, session=session)]

    starts = [c for c in spy.calls if c[0] == "emit_llm_call_start"]
    assert len(starts) == 1
    assert starts[0][1]["state"] is state
    assert starts[0][1]["session"] is session
    assert starts[0][1]["stream"] is True


async def test_stream_forwards_state_and_session_to_spine_emit_end() -> None:
    """``state`` / ``session`` reach ``emit_llm_call_end`` on the stream path."""
    spy = _SpySpine()
    state = _state()
    session = object()
    adapter = TelemetryLLMAdapter(_FakeInner(), spine_emit=spy)

    _events = [e async for e in adapter.stream("prompt", state=state, session=session)]

    ends = [c for c in spy.calls if c[0] == "emit_llm_call_end"]
    assert len(ends) == 1
    assert ends[0][1]["outcome"] == "success"
    assert ends[0][1]["state"] is state
    assert ends[0][1]["session"] is session


async def test_stream_forwards_state_and_session_to_emit_llm_stream_token() -> None:
    """Per-token ``emit_llm_stream_token`` carries ``state`` / ``session``."""
    spy = _SpySpine()
    state = _state()
    session = object()
    adapter = TelemetryLLMAdapter(_FakeInner(), spine_emit=spy)

    _events = [e async for e in adapter.stream("prompt", state=state, session=session)]

    tokens = [c for c in spy.calls if c[0] == "emit_llm_stream_token"]
    assert len(tokens) == 1
    assert tokens[0][1]["state"] is state
    assert tokens[0][1]["session"] is session


async def test_stream_strips_state_and_session_from_inner_kwargs() -> None:
    """Inner adapter's ``stream()`` never sees ``state`` / ``session``."""
    inner = _FakeInner()

    async def _record_stream(prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        inner.last_kwargs = dict(kwargs)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED)

    inner.stream = _record_stream  # type: ignore[assignment]
    adapter = TelemetryLLMAdapter(inner, spine_emit=_SpySpine())

    state = _state()
    session = object()
    _events = [e async for e in adapter.stream("prompt", state=state, session=session)]

    assert inner.last_kwargs is not None
    assert "state" not in inner.last_kwargs
    assert "session" not in inner.last_kwargs


async def test_complete_without_state_session_does_not_forward_them() -> None:
    """No ``state`` / ``session`` kwargs ⇒ the emit still happens with ``None`` values.

    Preserves the contract that ``state`` / ``session`` are always
    passed (so the seam is unconditional); only their value defaults
    to ``None`` when the caller omits them. The drop logic in
    ``publish_ep_bound`` handles the ``None`` case.
    """
    spy = _SpySpine()
    adapter = TelemetryLLMAdapter(_FakeInner(), spine_emit=spy)

    await adapter.complete("prompt", turn=5, step=2)

    starts = [c for c in spy.calls if c[0] == "emit_llm_call_start"]
    assert len(starts) == 1
    assert "state" in starts[0][1]
    assert starts[0][1]["state"] is None
    assert "session" in starts[0][1]
    assert starts[0][1]["session"] is None


async def test_stream_idle_timeout_fires_despite_non_progress_events() -> None:
    """Non-content events must not defeat the LLM stream idle timeout.

    Regression: a provider that starts streaming a tool call and never
    finishes it keeps the stream "alive" with ``FUNCTION_CALL_ARGUMENTS_DELTA``
    events. Those events reset the per-event ``wait_for`` deadline, so the
    stream hangs until a manual cancel. The idle guard must measure time
    since the last *content* delta (text or non-empty tool arguments), not
    since any event.
    """
    import asyncio

    class _NonProgressInner(_FakeInner):
        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
            del prompt, kwargs
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="hi")
            i = 0
            while True:
                yield LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=f"toolu_{i}",
                    tool_name=None,
                    arguments_delta="",
                )
                i += 1
                await asyncio.sleep(0.05)

    spy = _SpySpine()
    state = _state()
    session = object()
    adapter = TelemetryLLMAdapter(
        _NonProgressInner(),
        idle_timeout_s=0.5,
        spine_emit=spy,
    )

    async def _consume() -> None:
        async for _ in adapter.stream("prompt", state=state, session=session):
            pass

    # The stream must abort itself (TimeoutError) instead of hanging; the
    # outer deadline only bounds a regression where the guard never fires.
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(_consume(), timeout=10.0)

    ends = [c for c in spy.calls if c[0] == "emit_llm_call_end"]
    assert len(ends) == 1
    assert ends[0][1]["outcome"] == "timeout"
    assert ends[0][1]["state"] is state
    assert ends[0][1]["session"] is session
