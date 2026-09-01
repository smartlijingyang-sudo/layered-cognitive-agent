"""Tests for body + LLM spine reflector (PR-3.3).

Asserts that body layer entry points emit the canonical
``EXECUTION_POINTS`` events ``body.tool.execute.start/end``,
``body.sandbox.enter/exit``, ``body.tool.retry`` and that the LLM
layer emits ``llm.call.start/end`` and ``llm.stream.token`` when a
spine is wired. The emit helpers must also be safe no-ops when no
spine is wired.

The reflector module is the single emission site for these eight
execution points: every test exercises either the helper API or a
boundary in ``lca.cognition.body.safe_executor`` /
``lca.infrastructure.observability.adapters.adapters.TelemetryLLMAdapter``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine

# ── helpers ──────────────────────────────────────────────────────────


class _CaptureSink:
    """Minimal sink that records every EventRecord in order."""

    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_spine() -> tuple[EventSpine, _CaptureSink]:
    sink = _CaptureSink()
    spine = EventSpine(sinks=[sink])
    SpineContext.set_run("body-llm-reflector-test")
    return spine, sink


def _eps_by_point(records: list[EventRecord]) -> dict[str, list[EventRecord]]:
    out: dict[str, list[EventRecord]] = {}
    for rec in records:
        out.setdefault(rec.execution_point, []).append(rec)
    return out


def _run(coro: Any) -> Any:
    """Run an awaitable synchronously (test helper)."""
    import asyncio

    # 3.14 deprecates ``asyncio.get_event_loop`` when there is no running
    # loop; ``asyncio.run`` always builds a fresh one and tears it down.
    return asyncio.run(coro)


# ── safe no-ops without active spine ────────────────────────────────


def test_emit_helpers_are_safe_when_no_spine_wired() -> None:
    """Without an active spine, the helpers must not raise."""
    from lca.plugins.observability.spine.reflectors import body_llm

    set_spine = body_llm.set_active_spine
    set_spine(None)
    try:
        body_llm.emit_body_tool_execute_start(tool_name="t", invocation_id="i1")
        body_llm.emit_body_tool_execute_end(tool_name="t", invocation_id="i1", outcome="success")
        body_llm.emit_body_tool_retry(tool_name="t", invocation_id="i1", attempt=2, reason="boom")
        body_llm.emit_body_sandbox_enter(invocation_id="i1", tool_name="t")
        body_llm.emit_body_sandbox_exit(invocation_id="i1", tool_name="t")
        body_llm.emit_llm_call_start(model="m", stream=False)
        body_llm.emit_llm_call_end(model="m", stream=False, outcome="success")
        body_llm.emit_llm_stream_token(model="m", text_delta="hi", seq=0)
    finally:
        set_spine(None)


# ── helpers forward to active spine ──────────────────────────────────


def test_emit_helpers_forward_to_active_spine() -> None:
    """When a spine is set, helpers emit via spine.append with the right EP."""
    from lca.plugins.observability.spine.reflectors import body_llm

    spine, sink = _make_spine()
    body_llm.set_active_spine(spine)
    try:
        body_llm.emit_body_tool_execute_start(tool_name="t", invocation_id="i1")
        body_llm.emit_body_tool_execute_end(tool_name="t", invocation_id="i1", outcome="success")
        body_llm.emit_body_tool_retry(tool_name="t", invocation_id="i1", attempt=2, reason="x")
        body_llm.emit_body_sandbox_enter(invocation_id="i1", tool_name="t")
        body_llm.emit_body_sandbox_exit(invocation_id="i1", tool_name="t", outcome="success")
        body_llm.emit_llm_call_start(model="m", stream=False)
        body_llm.emit_llm_call_end(model="m", stream=False, outcome="success")
        body_llm.emit_llm_stream_token(model="m", text_delta="hi", seq=0)
    finally:
        body_llm.set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == [
        "body.tool.execute.start",
        "body.tool.execute.end",
        "body.tool.retry",
        "body.sandbox.enter",
        "body.sandbox.exit",
        "llm.call.start",
        "llm.call.end",
        "llm.stream.token",
    ]
    assert sink.records[1].outcome == "success"
    assert sink.records[2].outcome == "retrying"
    # payload sanity
    assert sink.records[0].payload["tool_name"] == "t"
    assert sink.records[3].payload["invocation_id"] == "i1"
    assert sink.records[5].payload["model"] == "m"
    assert sink.records[7].payload["text_delta"] == "hi"


# ── body.tool.execute.start/end via safe_executor ────────────────────


def test_simple_safe_executor_emits_body_tool_execute_start_end() -> None:
    """SafeExecutor.execute emits body.tool.execute.start/end around tool.execute."""
    from lca.cognition.body.safe_executor import SimpleSafeExecutor
    from lca.contracts.models.core.decision import Observation
    from lca.contracts.models.team.role_team import (
        CacheConfig,
        RetryPolicy,
        ToolPermissionManifest,
    )
    from lca.contracts.protocols import Tool
    from lca.plugins.observability.spine.reflectors import body_llm

    class _OkTool(Tool):
        name = "ok"
        description = "ok"
        parameters: ClassVar[dict[str, object]] = {}
        default_timeout_s = 30
        is_idempotent = True

        async def execute(self, args: dict[str, Any]) -> Observation:
            return Observation(
                observation_id="obs-ok",
                success=True,
                payload={"echo": args.get("x")},
            )

        def validate(self, args: dict[str, Any]) -> str | None:
            del args
            return None

    manifest = ToolPermissionManifest(allowed_tools=["ok"])
    executor = SimpleSafeExecutor(permission_manifest=manifest)

    spine, sink = _make_spine()
    body_llm.set_active_spine(spine)
    try:
        obs = _run(
            executor.execute(
                _OkTool(),
                {"x": 1},
                RetryPolicy(max_retries=0),
                CacheConfig(enabled=False),
                invocation_id="inv-1",
            )
        )
        assert obs.success
    finally:
        body_llm.set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    # body.tool.execute.start, body.sandbox.enter, body.tool.execute.end, body.sandbox.exit
    assert "body.tool.execute.start" in points
    assert "body.tool.execute.end" in points
    assert "body.sandbox.enter" in points
    assert "body.sandbox.exit" in points
    # start/end bracket sandbox enter/exit
    by_ep = _eps_by_point(sink.records)
    starts = [r.sequence for r in by_ep["body.tool.execute.start"]]
    ends = [r.sequence for r in by_ep["body.tool.execute.end"]]
    assert len(starts) == 1
    assert len(ends) == 1
    assert by_ep["body.tool.execute.end"][0].outcome == "success"


# ── body.tool.retry emitted when retry fires ────────────────────────


def test_simple_safe_executor_emits_body_tool_retry_on_transient_failure() -> None:
    """When the executor retries on transient failure, body.tool.retry fires."""
    from lca.cognition.body.safe_executor import SimpleSafeExecutor
    from lca.contracts.atoms.semantic_keys import (
        FAILURE_KIND,
        FAILURE_KIND_TRANSIENT,
    )
    from lca.contracts.models.core.decision import Observation
    from lca.contracts.models.team.role_team import (
        CacheConfig,
        RetryPolicy,
        ToolPermissionManifest,
    )
    from lca.contracts.protocols import Tool
    from lca.plugins.observability.spine.reflectors import body_llm

    class _FlakyTool(Tool):
        name = "flaky"
        description = "flaky"
        parameters: ClassVar[dict[str, object]] = {}
        default_timeout_s = 30
        is_idempotent = True

        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, args: dict[str, Any]) -> Observation:
            del args
            self.calls += 1
            if self.calls < 3:
                return Observation(
                    observation_id=f"obs-{self.calls}",
                    success=False,
                    payload=None,
                    error="transient",
                    extra={FAILURE_KIND: FAILURE_KIND_TRANSIENT},
                )
            return Observation(observation_id="obs-3", success=True, payload={"ok": True})

        def validate(self, args: dict[str, Any]) -> str | None:
            del args
            return None

    manifest = ToolPermissionManifest(allowed_tools=["flaky"])
    executor = SimpleSafeExecutor(permission_manifest=manifest)

    spine, sink = _make_spine()
    body_llm.set_active_spine(spine)
    try:
        tool = _FlakyTool()
        obs = _run(
            executor.execute(
                tool,
                {},
                RetryPolicy(max_retries=3, backoff_base_s=0.0, backoff_multiplier=1.0),
                CacheConfig(enabled=False),
                invocation_id="inv-flaky",
            )
        )
        assert obs.success
        assert tool.calls == 3
    finally:
        body_llm.set_active_spine(None)

    by_ep = _eps_by_point(sink.records)
    # First two attempts failed transiently; one retry → body.tool.retry fires once.
    assert "body.tool.retry" in by_ep
    # execute.start/end fire per attempt: 3 of each.
    assert len(by_ep["body.tool.execute.start"]) == 3
    assert len(by_ep["body.tool.execute.end"]) == 3
    retries = by_ep["body.tool.retry"]
    assert retries[0].outcome == "retrying"


# ── llm.call.start/end via TelemetryLLMAdapter ──────────────────────


def test_telemetry_llm_adapter_emits_llm_call_start_end_on_complete() -> None:
    """TelemetryLLMAdapter.complete wraps with llm.call.start/end."""
    from lca.contracts.models.core.llm import LLMResponse
    from lca.contracts.protocols import LLMAdapter
    from lca.infrastructure.observability.adapters.adapters import TelemetryLLMAdapter
    from lca.plugins.observability.spine.reflectors import body_llm

    class _InnerLLM(LLMAdapter):
        name = "stub-inner"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
            return LLMResponse(text="hello", tool_calls=(), finish_reason="stop")

        async def stream(self, prompt: str, **kwargs: Any):  # type: ignore[override]
            if False:
                yield None

    spine, sink = _make_spine()
    body_llm.set_active_spine(spine)
    try:
        adapter = TelemetryLLMAdapter(_InnerLLM())
        resp = _run(adapter.complete("hi"))
        assert resp.text == "hello"
    finally:
        body_llm.set_active_spine(None)

    by_ep = _eps_by_point(sink.records)
    assert "llm.call.start" in by_ep
    assert "llm.call.end" in by_ep
    assert by_ep["llm.call.end"][0].outcome == "success"
    # execute order: start before end
    start_seq = by_ep["llm.call.start"][0].sequence
    end_seq = by_ep["llm.call.end"][0].sequence
    assert start_seq < end_seq


def test_telemetry_llm_adapter_emits_llm_stream_token_on_stream() -> None:
    """TelemetryLLMAdapter.stream emits llm.stream.token per OUTPUT_TEXT_DELTA."""
    from collections.abc import AsyncIterator

    from lca.contracts.atoms.enums import LLMStreamEventType
    from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
    from lca.contracts.protocols import LLMAdapter
    from lca.infrastructure.observability.adapters.adapters import TelemetryLLMAdapter
    from lca.plugins.observability.spine.reflectors import body_llm

    class _InnerLLM(LLMAdapter):
        name = "stub-stream"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:  # type: ignore[override]
            del prompt, kwargs
            return LLMResponse(text="x", tool_calls=(), finish_reason="stop")

        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
            del prompt, kwargs
            for token in ("a", "b", "c"):
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=token)
            yield LLMStreamEvent(
                type=LLMStreamEventType.COMPLETED,
                response=LLMResponse(text="abc", tool_calls=(), finish_reason="stop"),
            )

    spine, sink = _make_spine()
    body_llm.set_active_spine(spine)
    try:
        adapter = TelemetryLLMAdapter(_InnerLLM())
        tokens: list[str] = []

        async def _consume() -> None:
            async for ev in adapter.stream("hi"):
                if ev.type == LLMStreamEventType.OUTPUT_TEXT_DELTA and ev.text:
                    tokens.append(ev.text)

        _run(_consume())
        assert tokens == ["a", "b", "c"]
    finally:
        body_llm.set_active_spine(None)

    by_ep = _eps_by_point(sink.records)
    # Exactly 3 OUTPUT_TEXT_DELTA events → 3 llm.stream.token.
    token_events = by_ep.get("llm.stream.token", [])
    assert len(token_events) == 3
    # The telemetry emits token with channel_kind=output. The seq reflects
    # delta_seq at emit time, which is incremented once before and once
    # after the answer-delta branch; we just need them to be monotonically
    # increasing integers (the contract is "per-output-delta seq ordering",
    # not "consecutive integers").
    output_tokens = [ev for ev in token_events if ev.payload.get("channel_kind") == "output"]
    assert len(output_tokens) == 3
    seqs = [ev.payload["seq"] for ev in output_tokens]
    assert seqs == sorted(seqs)
    # llm.call.start + llm.call.end bracket the stream
    assert "llm.call.start" in by_ep
    assert "llm.call.end" in by_ep
    assert by_ep["llm.call.end"][0].outcome == "success"


# ── exception path emits end with failure outcome ──────────────────


def test_telemetry_llm_adapter_emits_end_failure_on_inner_exception() -> None:
    """If the inner LLM raises, llm.call.end still fires with outcome='failure'."""
    from lca.contracts.models.core.llm import LLMResponse
    from lca.contracts.protocols import LLMAdapter
    from lca.infrastructure.observability.adapters.adapters import TelemetryLLMAdapter
    from lca.plugins.observability.spine.reflectors import body_llm

    class _BoomLLM(LLMAdapter):
        name = "stub-boom"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:  # type: ignore[override]
            del prompt, kwargs
            raise RuntimeError("provider down")

        async def stream(self, prompt: str, **kwargs: Any):  # type: ignore[override]
            del prompt, kwargs
            if False:
                yield None

    spine, sink = _make_spine()
    body_llm.set_active_spine(spine)
    try:
        adapter = TelemetryLLMAdapter(_BoomLLM())
        with pytest.raises(RuntimeError, match="provider down"):
            _run(adapter.complete("hi"))
    finally:
        body_llm.set_active_spine(None)

    by_ep = _eps_by_point(sink.records)
    assert "llm.call.start" in by_ep
    assert "llm.call.end" in by_ep
    assert by_ep["llm.call.end"][0].outcome == "failure"
