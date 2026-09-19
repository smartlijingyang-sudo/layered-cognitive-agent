"""LLM adapter decorator — Session EP emit + cursor advance (SSOT only).

ADR-0186 / ADR-0192: every durable fact routes through
``Session.append``. ``TelemetryLLMAdapter`` previously dual-wrote to
the legacy journal (``record(StepTextDelta/ReasoningDelta/LlmCallCompleted)``)
through ``facade.record()`` which only landed in ``InMemoryJournalStore``
plus projection fan-out — never the ``<run_id>.spine.jsonl``. That dual
path has zero readers outside descriptors/tests and is removed.

What stays:

- ``emit_llm_call_start`` / ``emit_llm_call_end`` → ``Session.append``
- ``emit_llm_stream_token`` (channel_kind reasoning | output) → ``Session.append``
- ``emit_llm_stream_stall`` (idle timeout) → ``Session.append``
- ``cursor.advance("think", ...)`` for ``phase.think.fold`` (cursor SSOT)

What goes:

- ``record(StepTextDelta)`` / ``record(ReasoningDelta)`` / ``record(LlmCallCompleted)``
- ``record_llm_completion`` (no spine EP for ``llm.complete``)
- The ``MemoryJournal`` ``record()`` facade, ``RunStore``, ``InMemoryJournalStore``
  — these are legacy journal storage and are still used by harness/test
  paths, so they remain at the storage layer; the active production
  emit path no longer writes to them.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import structlog

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.harness.memory.events import ThinkingCompleted, ThinkingDelta
from lca.contracts.models.core.conversation.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.observability.llm_spine_emit import LlmSpineEmitter
from lca.infrastructure.observability.stream.llm_stream_activity import (
    LlmStreamActivityTracker,
)

_PERF_COUNTER_SCALE = 1000

SessionAppend = Callable[[Any], Awaitable[object] | None]
"""Session thinking.* 注入口（optional, no-op when unbound）。

未注入 ``session_append`` 时 thinking events 静默丢弃；append 抛错向上传。
"""

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


def _stream_observability_kwargs(
    kwargs: dict[str, Any],
) -> tuple[int, int, object | None, object | None, dict[str, Any]]:
    """Extract observability kwargs (turn/step/state/session) for spine emit.

    state/session are forwarded alongside turn/step so the emit seam can
    bind the FactGateway writer (publish_ep_bound drops when both are
    unbound).
    """
    turn = kwargs.get("turn", 0)
    if not isinstance(turn, int):
        turn = 0
    step = kwargs.get("step", 0)
    if not isinstance(step, int):
        step = 0
    state = kwargs.get("state")
    session = kwargs.get("session")
    inner_kwargs = {
        k: v for k, v in kwargs.items() if k not in ("turn", "step", "state", "session")
    }
    return turn, step, state, session, inner_kwargs


def _maybe_fail_model(*, turn: int, step: int, error: str) -> None:
    """Emit ``model.failed.v1`` when step identity is known from kwargs."""
    if step <= 0:
        return
    from lca.infrastructure.session.emit.lifecycle_emit import fail_model

    turn_no = turn if turn > 0 else 1
    fail_model(turn=turn_no, step=step, error=error)


def _is_content_progress(event: LLMStreamEvent) -> bool:
    """True when the event carries actual LLM content progress.

    Protocol-only events (block boundaries, empty tool-call chunks) must not
    extend the idle deadline, or a provider that never finishes a tool call
    keeps the stream alive indefinitely.
    """
    if event.type in (
        LLMStreamEventType.COMPLETED,
        LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DONE,
    ):
        return True
    if event.type in (
        LLMStreamEventType.OUTPUT_TEXT_DELTA,
        LLMStreamEventType.REASONING_TEXT_DELTA,
    ):
        return bool(event.text)
    if event.type == LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA:
        return bool(event.arguments_delta)
    return False


class TelemetryLLMAdapter(LLMAdapter):
    """Decorator: Session EP emit only — no legacy journal writes.

    Owns LLM call boundary observability:

    - ``llm.call.start`` / ``llm.call.end`` via :class:`LlmSpineEmitter`
      (Session runtime → ``<run_id>.spine.jsonl``)
    - ``llm.stream.token`` per delta (reasoning | output)
    - ``llm.stream.stall`` on idle timeout
    - ``phase.think.fold`` via cursor SSOT (ADR-0169 P2)

    The class name stays for the assembly seam (``instrument_llm``);
    the behaviour is single-writer — no :func:`facade.record` calls.
    """

    name = "telemetry-llm"

    def __init__(
        self,
        inner: LLMAdapter,
        *,
        idle_timeout_s: float | None = None,
        session_append: SessionAppend | None = None,
        spine_emit: LlmSpineEmitter | None = None,
    ) -> None:
        self._inner = inner
        self.name = f"telemetry({getattr(inner, 'name', type(inner).__name__)})"
        from lca.infrastructure.observability.stream.llm_stream_activity import (
            LLM_STREAM_IDLE_TIMEOUT_S,
        )

        self._idle_timeout_s = (
            LLM_STREAM_IDLE_TIMEOUT_S if idle_timeout_s is None else idle_timeout_s
        )
        self._session_append = session_append
        self._spine_emit = spine_emit

    def _spine(self) -> LlmSpineEmitter:
        if self._spine_emit is not None:
            return self._spine_emit
        from lca.loop.emit.cognitive import llm

        return llm

    @property
    def inner(self) -> LLMAdapter:
        """Decorated adapter (composition introspection)."""
        return self._inner

    async def _append_thinking_session_event(self, payload: object) -> None:
        """Append thinking event to Session (optional injection)."""
        if self._session_append is None:
            return
        result = self._session_append(payload)
        if inspect.isawaitable(result):
            await result

    def _schedule_thinking_session_event(self, payload: object) -> None:
        """Fire-and-forget thinking delta — keep LLM stream unblocked."""
        if self._session_append is None:
            return
        append = self._session_append

        async def _run() -> None:
            try:
                result = append(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                _log.warning("thinking_session_append_failed", exc_info=True)

        # Reasoning deltas must not block the LLM read loop.
        _ = asyncio.create_task(_run())  # noqa: RUF006

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = _model_label(self._inner)
        started = time.perf_counter()
        _open_think_step(prompt)
        _turn, step, state, session, inner_kwargs = _stream_observability_kwargs(dict(kwargs))
        self._spine().emit_llm_call_start(
            model=model,
            stream=False,
            prompt_preview=prompt,
            state=state,
            session=session,
        )
        try:
            response = await self._inner.complete(prompt, **inner_kwargs)
        except Exception as exc:
            self._spine().emit_llm_call_end(
                model=model,
                stream=False,
                outcome="failure",
                latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
                state=state,
                session=session,
            )
            _maybe_fail_model(turn=_turn, step=step, error=str(exc))
            raise
        prompt_tokens, completion_tokens = _usage_of(response)
        self._spine().emit_llm_call_end(
            model=model,
            stream=False,
            outcome="success",
            latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            state=state,
            session=session,
        )
        _advance_think_fold(model=model, ok=True)
        return response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        model = _model_label(self._inner)
        started = time.perf_counter()
        reasoning_text = ""
        reasoning_started: float | None = None
        reasoning_seq = 0
        output_seq = 0
        final_response: LLMResponse | None = None
        turn, step, state, session, inner_kwargs = _stream_observability_kwargs(dict(kwargs))

        _open_think_step(prompt)
        self._spine().emit_llm_call_start(
            model=model,
            stream=True,
            prompt_preview=prompt,
            state=state,
            session=session,
        )

        # ``llm.call.end`` must fire in ``finally`` because consumers
        # ``_stream_turn`` ``break`` on COMPLETED, which injects GeneratorExit
        # and skips post-yield code on some paths.
        spine_end_emitted = False
        saw_completed = False
        end_outcome: str = "success"

        def _on_idle(idle_s: float, idle_seq: int) -> None:
            self._spine().emit_llm_stream_stall(
                model=model,
                idle_ms=int(idle_s * _PERF_COUNTER_SCALE),
                seq=idle_seq,
            )

        activity = LlmStreamActivityTracker(step=step, model=model, on_idle=_on_idle)
        activity.start()

        inner_stream = self._inner.stream(prompt, **inner_kwargs)
        try:
            while True:
                # Only content deltas reset the idle deadline; protocol-only
                # events (block boundaries, empty tool-call chunks) must not
                # keep a never-finishing tool-call stream alive forever.
                remaining = self._idle_timeout_s - activity.idle_s()
                try:
                    event = await asyncio.wait_for(
                        inner_stream.__anext__(),
                        timeout=max(0.0, remaining),
                    )
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    end_outcome = "timeout"
                    aclose_fn = getattr(inner_stream, "aclose", None)
                    if callable(aclose_fn):
                        with contextlib.suppress(Exception):
                            await cast("Any", aclose_fn)()
                    _log.warning(
                        "llm_stream_idle_timeout",
                        adapter=type(self._inner).__name__,
                        model=model,
                        idle_timeout_s=self._idle_timeout_s,
                    )
                    raise
                if _is_content_progress(event):
                    activity.touch()
                if event.type == LLMStreamEventType.COMPLETED:
                    saw_completed = True
                    if reasoning_text or reasoning_started is not None:
                        duration_ms = 0
                        if reasoning_started is not None:
                            duration_ms = int(
                                (time.perf_counter() - reasoning_started) * _PERF_COUNTER_SCALE
                            )
                        await self._append_thinking_session_event(
                            ThinkingCompleted(
                                turn=turn,
                                step=step,
                                duration_ms=duration_ms,
                                content_preview=reasoning_text,
                            )
                        )
                    final_response = event.response
                    if not spine_end_emitted:
                        pt, ct = _usage_of(final_response) if final_response is not None else (0, 0)
                        self._spine().emit_llm_call_end(
                            model=model,
                            stream=True,
                            outcome="success",
                            latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
                            prompt_tokens=pt or None,
                            completion_tokens=ct or None,
                            state=state,
                            session=session,
                        )
                        spine_end_emitted = True
                elif event.type == LLMStreamEventType.REASONING_TEXT_DELTA:
                    delta_text = event.text or ""
                    if delta_text:
                        if reasoning_started is None:
                            reasoning_started = time.perf_counter()
                        reasoning_text += delta_text
                        self._schedule_thinking_session_event(
                            ThinkingDelta(
                                turn=turn,
                                step=step,
                                text_delta=delta_text,
                                seq=reasoning_seq,
                            )
                        )
                        # ADR-0167 D4b / PR-3: reasoning delta coalesces into
                        # step.thinking.reasoning; per-token EP path is the
                        # spine ``llm.stream.token`` only.
                        self._spine().emit_llm_stream_token(
                            model=model,
                            text_delta=delta_text,
                            seq=reasoning_seq,
                            channel_kind="reasoning",
                            state=state,
                            session=session,
                        )
                        reasoning_seq += 1
                elif event.type == LLMStreamEventType.OUTPUT_TEXT_DELTA:
                    # The answer channel is a fact too: without this row the
                    # assistant body never reaches Session, so neither the
                    # journal step nor the gateway wire (``stream_chunk``
                    # ``chunkType: "text"``) can carry the reply.
                    delta_text = event.text or ""
                    if delta_text:
                        self._spine().emit_llm_stream_token(
                            model=model,
                            text_delta=delta_text,
                            seq=output_seq,
                            channel_kind="output",
                            state=state,
                            session=session,
                        )
                        output_seq += 1
                yield event
        except asyncio.CancelledError:
            end_outcome = "cancelled"
            raise
        except TimeoutError:
            end_outcome = "timeout"
            _maybe_fail_model(turn=turn, step=step, error="timeout")
            raise
        except Exception as exc:
            end_outcome = "failure"
            _maybe_fail_model(turn=turn, step=step, error=str(exc))
            raise
        finally:
            await activity.close()
            if not spine_end_emitted:
                outcome = end_outcome
                if outcome == "success" and not saw_completed:
                    outcome = "cancelled"
                prompt_tokens, completion_tokens = (
                    _usage_of(final_response) if final_response is not None else (0, 0)
                )
                self._spine().emit_llm_call_end(
                    model=model,
                    stream=True,
                    outcome=outcome,
                    latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    state=state,
                    session=session,
                )
            # Cursor advance for phase.think.fold is unconditional: every
            # LLM call resolves to either ``respond`` (success) or
            # ``error`` (failure). Skip on cancelled — the loop driver
            # owns that signal and emits its own fold.
            if end_outcome != "cancelled":
                _advance_think_fold(model=model, ok=(end_outcome == "success"))


def _advance_think_fold(*, model: str, ok: bool) -> None:
    """Close the think fold via cursor (SSOT for ``phase.think.fold``).

    ADR-0169 P2: cursor is the single writer; ``coord.*`` is forbidden.

    spec section H ContextVar deletion: cursor is sourced from
    :class:`CursorRecord` (explicit DI) instead of the deleted
    ``get_current_cursor()`` ContextVar.
    """
    from lca.cognition.body.executor.cursor_record import CursorRecord

    cursor = CursorRecord.get()
    if cursor is None:
        return
    cursor.advance(
        "think",
        objective_kind="model_name",
        objective=model,
        summary=("respond" if ok else "error"),
    )


def _open_think_step(prompt: str) -> None:
    """Emit think entry via cursor (SSOT).

    ADR-0169 P2: ``phase.<x>.fold`` is cursor-derived. objective must
    be the user prompt (kind ``user_text``); model name is recorded at
    fold time, not here.

    spec section H ContextVar deletion: cursor is sourced from
    :class:`CursorRecord` (explicit DI) instead of the deleted
    ``get_current_cursor()`` ContextVar.
    """
    from lca.cognition.body.executor.cursor_record import CursorRecord

    cursor = CursorRecord.get()
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


__all__ = ["TelemetryLLMAdapter"]
