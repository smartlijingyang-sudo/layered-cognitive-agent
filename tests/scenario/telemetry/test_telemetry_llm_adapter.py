"""TelemetryLLMAdapter contract tests — session EP emit only.

ADR-0186 / ADR-0192: every durable fact routes through
``Session.append``. ``TelemetryLLMAdapter`` no longer writes to the
legacy ``MemoryJournal`` (``facade.record``). This file asserts:

- :func:`emit_llm_call_start` fires on entry, :func:`emit_llm_call_end`
  fires with the right outcome on every exit path.
- :func:`emit_llm_stream_token` fires per delta on the reasoning channel.
- :func:`ThinkingDelta` / :func:`ThinkingCompleted` reach the bound
  ``session_append`` when reasoning fires.
- :func:`facade.record` is **not** called. The legacy journal path
  is dead.

The ``session_publish`` fixture (publish_via_session) is the same one
``test_session_publish.py`` uses; it stands up a session + EventBus and
binds the global publish context so :func:`emit_llm_stream_token` /
:func:`emit_llm_call_*` actually land in a Session log we can read.
"""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.harness.memory.events import ThinkingCompleted, ThinkingDelta
from lca.contracts.harness.tasks.session import event_type_of
from lca.contracts.models.core.conversation.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.observability.adapters import TelemetryLLMAdapter
from lca.infrastructure.observability.adapters import adapters as _adapter_mod
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session
from lca_kernel.events.bus.bus import EventBus
from lca_kernel.events.test.catalog import build_test_bus


class _FakeInner(LLMAdapter):
    name = "fake-inner"
    fail: bool = False
    omit_completed: bool = False
    emit_reasoning: bool = False

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        if self.fail:
            raise RuntimeError("boom")
        return LLMResponse(
            text="done",
            model="fake-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        if self.fail:
            raise RuntimeError("stream boom")
        if self.emit_reasoning:
            yield LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text="想")
            yield LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text="一下")
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="hel")
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="lo")
        if not self.omit_completed:
            response = LLMResponse(
                text="hello",
                model="fake-model",
                usage=TokenUsage(prompt_tokens=20, completion_tokens=8),
            )
            yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


def _published_session_events(session: Session) -> list[tuple[str, dict[str, Any]]]:
    """Extract (execution_point, payload) pairs from the Session log.

    SessionEvent shape: ``type`` = category (``spine.X.Y``), ``data``
    holds ``{execution_point, payload, channel, ...}``. We pair
    execution_point with its payload for assertion-friendly matching.
    """
    events = session.snapshot_events() if hasattr(session, "snapshot_events") else []
    out: list[tuple[str, dict[str, Any]]] = []
    for e in events:
        ep = e.data.get("execution_point", e.type)
        payload = e.data.get("payload", {})
        out.append((ep, payload))
    return out


class TestTelemetryLLMAdapter(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Hard contract: the legacy facade.record symbol must not be
        # imported into the adapters module. Any regression that
        # re-imports it breaks here.
        self.assertFalse(
            hasattr(_adapter_mod, "record"),
            "TelemetryLLMAdapter must not import facade.record (ADR-0192 SSOT)",
        )
        EventBus.set_default(build_test_bus())
        self._session = Session("telemetry-adapter-test")
        self._session_token = set_publish_session(self._session)

    def tearDown(self) -> None:
        reset_publish_session(self._session_token)
        EventBus.set_default(None)

    async def test_complete_success_emits_llm_call_start_end(self) -> None:
        adapter = TelemetryLLMAdapter(_FakeInner())
        result = await adapter.complete("prompt")
        self.assertEqual(result.text, "done")

        emitted = _published_session_events(self._session)
        starts = [e for e in emitted if e[0] == "llm.call.start"]
        ends = [e for e in emitted if e[0] == "llm.call.end"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0][1]["stream"], False)
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0][1]["outcome"], "success")
        self.assertEqual(ends[0][1]["prompt_tokens"], 10)
        self.assertEqual(ends[0][1]["completion_tokens"], 5)

    async def test_complete_failure_emits_failure_end(self) -> None:
        inner = _FakeInner()
        inner.fail = True
        adapter = TelemetryLLMAdapter(inner)
        with self.assertRaises(RuntimeError):
            await adapter.complete("prompt")

        emitted = _published_session_events(self._session)
        ends = [e for e in emitted if e[0] == "llm.call.end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0][1]["outcome"], "failure")

    async def test_stream_emits_per_token_reasoning_to_session(self) -> None:
        inner = _FakeInner()
        inner.emit_reasoning = True
        adapter = TelemetryLLMAdapter(inner)
        events = [e async for e in adapter.stream("prompt", step=2, turn=1)]
        self.assertEqual(len(events), 5)

        emitted = _published_session_events(self._session)
        reasoning_tokens = [
            e
            for e in emitted
            if e[0] == "llm.stream.token" and e[1].get("channel_kind") == "reasoning"
        ]
        self.assertEqual(len(reasoning_tokens), 2)
        self.assertEqual(reasoning_tokens[0][1]["text_delta"], "想")
        self.assertEqual(reasoning_tokens[1][1]["text_delta"], "一下")
        self.assertEqual(reasoning_tokens[0][1]["seq"], 0)
        self.assertEqual(reasoning_tokens[1][1]["seq"], 1)

        ends = [e for e in emitted if e[0] == "llm.call.end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0][1]["outcome"], "success")
        self.assertEqual(ends[0][1]["prompt_tokens"], 20)
        self.assertEqual(ends[0][1]["completion_tokens"], 8)

    async def test_stream_session_append_receives_thinking_events(self) -> None:
        inner = _FakeInner()
        inner.emit_reasoning = True
        appended: list[Any] = []

        async def session_append(payload: Any) -> None:
            appended.append(payload)

        adapter = TelemetryLLMAdapter(inner, session_append=session_append)
        events = [e async for e in adapter.stream("prompt", step=3, turn=2)]
        self.assertEqual(len(events), 5)

        deltas = [p for p in appended if isinstance(p, ThinkingDelta)]
        self.assertEqual(len(deltas), 2)
        self.assertEqual(deltas[0].turn, 2)
        self.assertEqual(deltas[0].step, 3)
        self.assertEqual(deltas[0].text_delta, "想")
        self.assertEqual(deltas[0].seq, 0)
        self.assertEqual(deltas[1].text_delta, "一下")
        self.assertEqual(deltas[1].seq, 1)
        done = [p for p in appended if isinstance(p, ThinkingCompleted)]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0].content_preview, "想一下")
        self.assertGreaterEqual(done[0].duration_ms, 0)
        self.assertEqual(event_type_of(deltas[0]), "thinking.delta.v1")
        self.assertEqual(event_type_of(done[0]), "thinking.completed.v1")

    async def test_stream_session_append_accepts_sync_callable(self) -> None:
        inner = _FakeInner()
        inner.emit_reasoning = True
        appended: list[Any] = []
        adapter = TelemetryLLMAdapter(inner, session_append=appended.append)
        _events = [e async for e in adapter.stream("prompt", step=1)]
        self.assertEqual(len(appended), 3)
        self.assertEqual(sum(isinstance(p, ThinkingDelta) for p in appended), 2)
        self.assertEqual(sum(isinstance(p, ThinkingCompleted) for p in appended), 1)
        self.assertEqual(appended[0].turn, 0)

    async def test_stream_session_append_skipped_without_reasoning(self) -> None:
        appended: list[Any] = []

        async def session_append(payload: Any) -> None:
            appended.append(payload)

        adapter = TelemetryLLMAdapter(_FakeInner(), session_append=session_append)
        events = [e async for e in adapter.stream("prompt")]
        self.assertEqual(len(events), 3)
        self.assertEqual(appended, [])

    async def test_stream_missing_completed_emits_cancelled_end(self) -> None:
        inner = _FakeInner()
        inner.omit_completed = True
        adapter = TelemetryLLMAdapter(inner)
        events = [e async for e in adapter.stream("prompt")]
        self.assertEqual(len(events), 2)

        emitted = _published_session_events(self._session)
        ends = [e for e in emitted if e[0] == "llm.call.end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0][1]["outcome"], "cancelled")

    async def test_stream_failure_emits_failure_end(self) -> None:
        inner = _FakeInner()
        inner.fail = True
        adapter = TelemetryLLMAdapter(inner)
        with self.assertRaises(RuntimeError):
            [e async for e in adapter.stream("prompt")]

        emitted = _published_session_events(self._session)
        ends = [e for e in emitted if e[0] == "llm.call.end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0][1]["outcome"], "failure")


if __name__ == "__main__":
    unittest.main()
