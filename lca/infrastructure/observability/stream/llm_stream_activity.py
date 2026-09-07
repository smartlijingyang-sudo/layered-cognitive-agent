"""LLM stream activity heartbeat — emits ``llm.stream.stall`` during long waits.

Session SSOT only. ``RunActivity`` legacy journal event was emitted to
``MemoryJournal`` which had zero readers outside descriptors and tests;
deleted with the legacy journal write path (ADR-0192).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable

LLM_ACTIVITY_HEARTBEAT_S: float = 5.0
"""Emit llm.stream.stall when no LLM delta for this many seconds."""

LLM_STREAM_IDLE_TIMEOUT_S: float = 60.0
"""Abort an in-flight LLM stream after this many seconds without a delta.

Inter-token (and first-token) idle guard for provider stalls such as
``run_a3a442ff00aa`` — partial output then silence until manual cancel.
"""

IdleCallback = Callable[[float, int], None]
"""``on_idle(idle_s, seq)`` — optional spine/diagnostic hook."""


class LlmStreamActivityTracker:
    """Background heartbeat while an LLM stream is in flight.

    Owns the idle-detection loop only. ``llm.stream.stall`` emission
    is delegated to ``on_idle`` (provided by ``TelemetryLLMAdapter``
    which holds the Session EP emit context).
    """

    def __init__(
        self,
        *,
        step: int,
        model: str,
        on_idle: IdleCallback | None = None,
    ) -> None:
        self._step = step
        self._model = model
        self._on_idle = on_idle
        self._seq = 0
        self._last_delta_at = time.monotonic()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._heartbeat_loop())

    def touch(self) -> None:
        self._last_delta_at = time.monotonic()

    async def close(self) -> None:
        self._closed = True
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(LLM_ACTIVITY_HEARTBEAT_S)
                idle_s = time.monotonic() - self._last_delta_at
                if idle_s >= LLM_ACTIVITY_HEARTBEAT_S - 0.25:
                    if self._on_idle is not None:
                        self._on_idle(idle_s, self._seq)
                    self._seq += 1
        except asyncio.CancelledError:
            raise
