"""观测装饰器（Decorator 模式）—— 组合根装配，业务代码零埋点。

- ``TelemetryLLMAdapter``：LLM 调用 → journal ``LlmCallCompleted``
  （OTel 投影为 generation，gen_ai 语义约定 + token/成本自动核算）；
- ``TelemetryMemoryAdapter``：记忆读写 → memory.read / memory.write span
  （机制平面，verbose 档调试细节）。
"""

from __future__ import annotations

import asyncio
import contextlib
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
from lca.infrastructure.observability.stream.llm_stream_activity import (
    LLM_STREAM_IDLE_TIMEOUT_S,
    LlmStreamActivityTracker,
)
from lca.infrastructure.observability.stream.response_text_stream import ResponseTextStreamExtractor
from lca.plugins.observability.spine.reflectors import body_llm as _body_llm_reflector

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

    def __init__(
        self,
        inner: LLMAdapter,
        *,
        idle_timeout_s: float | None = None,
    ) -> None:
        self._inner = inner
        self.name = f"telemetry({getattr(inner, 'name', type(inner).__name__)})"
        self._idle_timeout_s = (
            LLM_STREAM_IDLE_TIMEOUT_S if idle_timeout_s is None else idle_timeout_s
        )

    @property
    def inner(self) -> LLMAdapter:
        """被装饰的 LLM 适配器（组合无损性内省用）。"""
        return self._inner

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = _model_label(self._inner)
        started = time.perf_counter()
        # ADR-0164: open think step at LLM boundary (auto dual-write seam).
        _open_think_step(prompt)
        # PR-3.3: spine emits llm.call.start/end around the inner call.
        # The journal ``record()`` pair (LlmCallStarted / LlmCallCompleted)
        # remains for backward compatibility with the legacy projector
        # pipeline; the spine pair is additive.
        _body_llm_reflector.emit_llm_call_start(
            model=model,
            stream=False,
            prompt_preview=prompt,
        )
        try:
            response = await self._inner.complete(prompt, **kwargs)
        except Exception:
            self._record(model, prompt, "", False, started, 0, 0, stream=False)
            _body_llm_reflector.emit_llm_call_end(
                model=model,
                stream=False,
                outcome="failure",
                latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
            )
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
        _body_llm_reflector.emit_llm_call_end(
            model=model,
            stream=False,
            outcome="success",
            latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
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

        # ADR-0164: open think step at LLM stream boundary.
        _open_think_step(prompt)
        record(LlmCallStarted(step=step, model=model))
        # PR-3.3: spine emits llm.call.start at the beginning of the stream.
        _body_llm_reflector.emit_llm_call_start(
            model=model,
            stream=True,
            prompt_preview=prompt,
        )
        # llm.call.end must fire in ``finally``: consumers (``_stream_turn``)
        # ``break`` on COMPLETED, which injects GeneratorExit and skips any
        # code after the async-for. CancelledError is BaseException and also
        # skipped the old ``except Exception`` end emit.
        spine_end_emitted = False
        saw_completed = False
        end_outcome: str = "success"

        def _on_idle(idle_s: float, idle_seq: int) -> None:
            _body_llm_reflector.emit_llm_stream_stall(
                model=model,
                idle_ms=int(idle_s * _PERF_COUNTER_SCALE),
                seq=idle_seq,
            )

        activity = LlmStreamActivityTracker(step=step, model=model, on_idle=_on_idle)
        activity.start()

        inner_stream = self._inner.stream(prompt, **inner_kwargs)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        inner_stream.__anext__(),
                        timeout=self._idle_timeout_s,
                    )
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    end_outcome = "timeout"
                    with contextlib.suppress(Exception):
                        await inner_stream.aclose()
                    _log.warning(
                        "llm_stream_idle_timeout",
                        adapter=type(self._inner).__name__,
                        model=model,
                        idle_timeout_s=self._idle_timeout_s,
                    )
                    raise
                activity.touch()
                if event.type == LLMStreamEventType.COMPLETED:
                    saw_completed = True
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
                            reasoning_text=reasoning_text,
                        )
                        recorded = True
                    # Emit success end BEFORE yielding COMPLETED. Consumers
                    # (``_stream_turn``) break on COMPLETED, which aclose()s the
                    # generator and can lose post-yield finally state on some
                    # paths; bracketing here keeps llm.call.end durable.
                    if not spine_end_emitted:
                        pt, ct = _usage_of(final_response) if final_response is not None else (0, 0)
                        _body_llm_reflector.emit_llm_call_end(
                            model=model,
                            stream=True,
                            outcome="success",
                            latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
                            prompt_tokens=pt or None,
                            completion_tokens=ct or None,
                        )
                        spine_end_emitted = True
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
                        # ADR-0167 D4b / PR-3: 流式 delta 由 coalescer 合并后落
                        # step.thinking.reasoning，不按 token 写 EP / span —— bridge 已删。
                        _body_llm_reflector.emit_llm_stream_token(
                            model=model,
                            text_delta=delta_text,
                            seq=reasoning_seq,
                            channel_kind="reasoning",
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
                    # ADR-0167 D4b / PR-3: 流式 delta 不写 EP / span（已删 bridge_*）
                    _body_llm_reflector.emit_llm_stream_token(
                        model=model,
                        text_delta=delta_text,
                        seq=delta_seq,
                        channel_kind="output",
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
        except asyncio.CancelledError:
            end_outcome = "cancelled"
            if not recorded:
                preview = final_response.text if final_response is not None else accumulated_text
                self._record(
                    model,
                    prompt,
                    preview,
                    False,
                    started,
                    0,
                    0,
                    stream=True,
                    reasoning_text=reasoning_text,
                )
            raise
        except TimeoutError:
            end_outcome = "timeout"
            if not recorded:
                preview = final_response.text if final_response is not None else accumulated_text
                self._record(
                    model,
                    prompt,
                    preview,
                    False,
                    started,
                    0,
                    0,
                    stream=True,
                    reasoning_text=reasoning_text,
                )
            raise
        except Exception:
            end_outcome = "failure"
            if not recorded:
                preview = final_response.text if final_response is not None else accumulated_text
                self._record(
                    model,
                    prompt,
                    preview,
                    False,
                    started,
                    0,
                    0,
                    stream=True,
                    reasoning_text=reasoning_text,
                )
            raise
        finally:
            await activity.close()
            if not recorded and end_outcome == "success":
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
                    reasoning_text=reasoning_text,
                )
            if not spine_end_emitted:
                outcome = end_outcome
                if outcome == "success" and not saw_completed:
                    outcome = "cancelled"
                prompt_tokens, completion_tokens = (
                    _usage_of(final_response) if final_response is not None else (0, 0)
                )
                _body_llm_reflector.emit_llm_call_end(
                    model=model,
                    stream=True,
                    outcome=outcome,  # type: ignore[arg-type]
                    latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                )
                spine_end_emitted = True

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
        reasoning_text: str = "",
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
                reasoning_preview=reasoning_text[:1024],
            )
        )
        # SSOT:phase.think.fold 由 cursor 唯一派生(ADR-0169 P2)。
        # 历史 bug:此路径曾用 coord.emit_phase 把 ``model=`` 误传成 ``objective=``,
        # 导致 spine 同 EP 出现 objective=模型名 与 objective=用户文本两条。
        # 修复:直接走 cursor.advance,objective_kind 显式 ``model_name``。
        from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
            get_current_cursor,
        )

        cursor = get_current_cursor()
        if cursor is not None:
            cursor.advance(
                "think",
                objective_kind="model_name",
                objective=model,
                summary=("respond" if ok else "error"),
            )


def _open_think_step(prompt: str) -> None:
    """Emit think 边 via cursor —— cursor 是唯一 writer(SSOT 收口)。

    ADR-0169 P2:phase.<x>.fold 由 cursor.advance 派生,禁止 coord 双写。
    objective 必须是用户原文,显式标 ``user_text``。
    """
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        get_current_cursor,
    )

    cursor = get_current_cursor()
    if cursor is None:
        return
    objective = (prompt or "").strip().replace("\n", " ")
    if len(objective) > 200:
        objective = objective[:200] + "…"
    cursor.advance(
        "think",
        objective_kind="user_text",
        objective=objective or "llm.complete",
        summary="started",
    )
