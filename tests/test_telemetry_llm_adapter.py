"""TelemetryLLMAdapter 单元测试 —— journal 记录与 stream 字段修复。"""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator
from typing import Any
from unittest import mock

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.models.observability.journal import (
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    StepTextDelta,
)
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.observability.adapters import TelemetryLLMAdapter


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


class TestTelemetryLLMAdapter(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.recorded: list[Any] = []
        self.record_patcher = mock.patch(
            "lca.infrastructure.observability.adapters.record",
            side_effect=lambda event: self.recorded.append(event),
        )
        self.record_patcher.start()

    def tearDown(self) -> None:
        self.record_patcher.stop()

    async def test_complete_success_records_tokens_and_stream_false(self) -> None:
        adapter = TelemetryLLMAdapter(_FakeInner())
        result = await adapter.complete("prompt")
        self.assertEqual(result.text, "done")
        self.assertEqual(len(self.recorded), 1)
        event = self.recorded[0]
        self.assertTrue(event.ok)
        self.assertEqual(event.prompt_tokens, 10)
        self.assertEqual(event.completion_tokens, 5)
        self.assertFalse(event.stream)

    async def test_complete_failure_records_stream_false(self) -> None:
        inner = _FakeInner()
        inner.fail = True
        adapter = TelemetryLLMAdapter(inner)
        with self.assertRaises(RuntimeError):
            await adapter.complete("prompt")
        self.assertEqual(len(self.recorded), 1)
        self.assertFalse(self.recorded[0].ok)
        self.assertFalse(self.recorded[0].stream)

    async def test_stream_records_step_text_deltas_before_yield(self) -> None:
        adapter = TelemetryLLMAdapter(_FakeInner())
        events = [e async for e in adapter.stream("prompt", step=2)]
        self.assertEqual(len(events), 3)
        deltas = [e for e in self.recorded if isinstance(e, StepTextDelta)]
        self.assertEqual(len(deltas), 4)
        decision = [d for d in deltas if d.channel == "decision"]
        answer = [d for d in deltas if d.channel == "answer"]
        self.assertEqual(len(decision), 2)
        self.assertEqual(len(answer), 2)
        self.assertEqual("".join(d.text_delta for d in decision), "hello")
        self.assertEqual("".join(d.text_delta for d in answer), "hello")
        completed = [e for e in self.recorded if isinstance(e, LlmCallCompleted)]
        self.assertEqual(len(completed), 1)

    async def test_stream_decision_json_answer_channel_only_response_text(self) -> None:
        class _JsonInner(_FakeInner):
            async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
                parts = [
                    '{"action_type": "respond", "rationale": "x", ',
                    '"response_text": "你',
                    '好"}',
                ]
                for part in parts:
                    yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=part)
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED,
                    response=LLMResponse(text="".join(parts), model="fake-model"),
                )

        adapter = TelemetryLLMAdapter(_JsonInner())
        _events = [e async for e in adapter.stream("prompt", step=1)]
        decision = [
            e for e in self.recorded if isinstance(e, StepTextDelta) and e.channel == "decision"
        ]
        answer = [
            e for e in self.recorded if isinstance(e, StepTextDelta) and e.channel == "answer"
        ]
        self.assertGreaterEqual(len(decision), 3)
        self.assertEqual("".join(d.text_delta for d in answer), "你好")
        joined_answer = "".join(d.text_delta for d in answer)
        self.assertNotIn("rationale", joined_answer)

    async def test_stream_uses_completed_tokens(self) -> None:
        adapter = TelemetryLLMAdapter(_FakeInner())
        events = [e async for e in adapter.stream("prompt")]
        self.assertEqual(len(events), 3)
        completed = [e for e in self.recorded if isinstance(e, LlmCallCompleted)]
        self.assertEqual(len(completed), 1)
        event = completed[0]
        self.assertTrue(event.ok)
        self.assertEqual(event.prompt_tokens, 20)
        self.assertEqual(event.completion_tokens, 8)
        self.assertTrue(event.stream)
        self.assertEqual(event.response_preview, "hello")

    async def test_stream_missing_completed_degrades_with_warning(self) -> None:
        inner = _FakeInner()
        inner.omit_completed = True
        with mock.patch("lca.infrastructure.observability.adapters._log") as log_mock:
            adapter = TelemetryLLMAdapter(inner)
            events = [e async for e in adapter.stream("prompt")]
        self.assertEqual(len(events), 2)
        completed = [e for e in self.recorded if isinstance(e, LlmCallCompleted)]
        self.assertEqual(len(completed), 1)
        event = completed[0]
        self.assertTrue(event.ok)
        self.assertEqual(event.prompt_tokens, 0)
        self.assertEqual(event.completion_tokens, 0)
        self.assertTrue(event.stream)
        self.assertEqual(event.response_preview, "hello")
        log_mock.warning.assert_called_once()

    async def test_stream_failure_records_stream_true(self) -> None:
        inner = _FakeInner()
        inner.fail = True
        adapter = TelemetryLLMAdapter(inner)
        with self.assertRaises(RuntimeError):
            [e async for e in adapter.stream("prompt")]
        completed = [e for e in self.recorded if isinstance(e, LlmCallCompleted)]
        self.assertEqual(len(completed), 1)
        self.assertFalse(completed[0].ok)
        self.assertTrue(completed[0].stream)
        started = [e for e in self.recorded if isinstance(e, LlmCallStarted)]
        self.assertEqual(len(started), 1)

    async def test_stream_reasoning_deltas_and_completed(self) -> None:
        inner = _FakeInner()
        inner.emit_reasoning = True
        adapter = TelemetryLLMAdapter(inner)
        events = [e async for e in adapter.stream("prompt", step=3)]
        self.assertEqual(len(events), 5)
        reasoning = [e for e in self.recorded if isinstance(e, ReasoningDelta)]
        self.assertEqual(len(reasoning), 2)
        self.assertEqual(reasoning[0].step, 3)
        self.assertEqual(reasoning[0].text_delta, "想")
        self.assertEqual(reasoning[1].seq, 1)
        done = [e for e in self.recorded if isinstance(e, ReasoningCompleted)]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0].step, 3)
        self.assertEqual(done[0].content_preview, "想一下")
        self.assertGreaterEqual(done[0].duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
