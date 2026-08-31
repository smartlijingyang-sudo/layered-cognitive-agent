"""观测装饰器（Decorator 模式）—— 组合根装配，业务代码零埋点。

- ``TelemetryLLMAdapter``：LLM 调用 → journal ``LlmCallCompleted``
  （OTel 投影为 generation，gen_ai 语义约定 + token/成本自动核算）；
- ``TelemetryMemoryAdapter``：记忆读写 → memory.read / memory.write span
  （机制平面，verbose 档调试细节）。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from lca.contracts.atoms.enums import LLMStreamEventType, StreamChannel
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.observability.journal import (
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    StepTextDelta,
)
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.observability.adapters.memory_adapter import (
    TelemetryMemoryAdapter as TelemetryMemoryAdapter,
)
from lca.infrastructure.observability.diagnostics.diagnostic_emitters import record_llm_completion
from lca.infrastructure.observability.facade.facade import record
from lca.infrastructure.observability.stream.llm_stream_activity import LlmStreamActivityTracker
from lca.infrastructure.observability.stream.response_text_stream import ResponseTextStreamExtractor

_PERF_COUNTER_SCALE = 1000
"""perf_counter 秒 → 毫秒换算。"""

_log = structlog.get_logger("lca.telemetry_llm")


def _model_label(inner: LLMAdapter) -> str:
    model = getattr(inner, "_model", None)
    if isinstance(model, str) and model:
        return model
    name = getattr(inner, "name", None)
    if isinstance(name, str) and name:
        return name
    return type(inner).__name__


def _usage_of(response: LLMResponse) -> tuple[int, int]:
    usage = response.usage
    if usage is None:
        return 0, 0
    return usage.prompt_tokens or 0, usage.completion_tokens or 0


def _stream_observability_kwargs(kwargs: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Extract journal ``step`` before forwarding kwargs to provider adapters."""
    step = kwargs.get("step", 0)
    if not isinstance(step, int):
        step = 0
    inner_kwargs = {k: v for k, v in kwargs.items() if k != "step"}
    return step, inner_kwargs


class TelemetryLLMAdapter(LLMAdapter):
    """装饰器：LLM 边界记录 LlmCallCompleted，不持有后端（ambient journal）。"""

    name = "telemetry-llm"

    def __init__(self, inner: LLMAdapter) -> None:
        self._inner = inner
        self.name = f"telemetry({getattr(inner, 'name', type(inner).__name__)})"

    @property
    def inner(self) -> LLMAdapter:
        """被装饰的 LLM 适配器（组合无损性内省用）。"""
        return self._inner

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = _model_label(self._inner)
        started = time.perf_counter()
        try:
            response = await self._inner.complete(prompt, **kwargs)
        except Exception:
            self._record(model, prompt, "", False, started, 0, 0, stream=False)
            raise
        prompt_tokens, completion_tokens = _usage_of(response)
        self._record(
            model,
            prompt,
            response.text,
            True,
            started,
            prompt_tokens,
            completion_tokens,
            stream=False,
        )
        return response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        model = _model_label(self._inner)
        started = time.perf_counter()
        accumulated_text = ""
        reasoning_text = ""
        reasoning_started: float | None = None
        reasoning_seq = 0
        final_response: LLMResponse | None = None
        step, inner_kwargs = _stream_observability_kwargs(dict(kwargs))
        delta_seq = 0
        recorded = False
        answer_extractor = ResponseTextStreamExtractor()

        record(LlmCallStarted(step=step, model=model))
        activity = LlmStreamActivityTracker(step=step, model=model)
        activity.start()

        try:
            async for event in self._inner.stream(prompt, **inner_kwargs):
                activity.touch()
                if event.type == LLMStreamEventType.COMPLETED:
                    if reasoning_text or reasoning_started is not None:
                        duration_ms = 0
                        if reasoning_started is not None:
                            duration_ms = int(
                                (time.perf_counter() - reasoning_started) * _PERF_COUNTER_SCALE
                            )
                        record(
                            ReasoningCompleted(
                                step=step,
                                duration_ms=duration_ms,
                                content_preview=reasoning_text,
                            )
                        )
                    final_response = event.response
                    if final_response is not None:
                        prompt_tokens, completion_tokens = _usage_of(final_response)
                        self._record(
                            model,
                            prompt,
                            final_response.text,
                            True,
                            started,
                            prompt_tokens,
                            completion_tokens,
                            stream=True,
                        )
                        recorded = True
                elif event.type == LLMStreamEventType.REASONING_TEXT_DELTA:
                    delta_text = event.text or ""
                    if delta_text:
                        if reasoning_started is None:
                            reasoning_started = time.perf_counter()
                        reasoning_text += delta_text
                        record(
                            ReasoningDelta(
                                step=step,
                                text_delta=delta_text,
                                seq=reasoning_seq,
                            )
                        )
                        reasoning_seq += 1
                elif event.type == LLMStreamEventType.OUTPUT_TEXT_DELTA:
                    delta_text = event.text or ""
                    accumulated_text += delta_text
                    record(
                        StepTextDelta(
                            step=step,
                            text_delta=delta_text,
                            seq=delta_seq,
                            channel=StreamChannel.DECISION.value,
                        )
                    )
                    delta_seq += 1
                    answer_delta = answer_extractor.feed(delta_text)
                    if answer_delta:
                        record(
                            StepTextDelta(
                                step=step,
                                text_delta=answer_delta,
                                seq=delta_seq,
                                channel=StreamChannel.ANSWER.value,
                            )
                        )
                        delta_seq += 1
                yield event
        except Exception:
            if not recorded:
                preview = final_response.text if final_response is not None else accumulated_text
                self._record(model, prompt, preview, False, started, 0, 0, stream=True)
            raise
        finally:
            await activity.close()

        if not recorded:
            _log.warning(
                "inner_adapter_stream_missing_completed",
                adapter=type(self._inner).__name__,
            )
            self._record(
                model,
                prompt,
                accumulated_text,
                True,
                started,
                0,
                0,
                stream=True,
            )

    @staticmethod
    def _record(
        model: str,
        prompt: str,
        response_text: str,
        ok: bool,
        started: float,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        stream: bool,
    ) -> None:
        latency_ms = int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)
        record_llm_completion(
            model=model,
            stream=stream,
            ok=ok,
            prompt=prompt,
            prompt_tokens=prompt_tokens,
            response_text=response_text,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
        record(
            LlmCallCompleted(
                model=model,
                ok=ok,
                latency_ms=latency_ms,
                prompt_preview=prompt,
                response_preview=response_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                stream=stream,
            )
        )
