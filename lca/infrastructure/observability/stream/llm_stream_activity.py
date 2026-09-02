"""LLM stream activity heartbeat — RunActivity during long model waits (ADR-0051)."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable

from lca.contracts.atoms.enums import RunActivityPhase
from lca.contracts.models.observability.journal import RunActivity
from lca.infrastructure.observability.facade.facade import record

LLM_ACTIVITY_HEARTBEAT_S: float = 5.0
"""Emit RunActivity when no LLM delta for this many seconds."""

LLM_STREAM_IDLE_TIMEOUT_S: float = 60.0
"""Abort an in-flight LLM stream after this many seconds without a delta.

Inter-token (and first-token) idle guard for provider stalls such as
``run_a3a442ff00aa`` — partial output then silence until manual cancel.
"""

IdleCallback = Callable[[float, int], None]
"""``on_idle(idle_s, seq)`` — optional spine/diagnostic hook."""


class LlmStreamActivityTracker:
    """Background heartbeat while an LLM stream is in flight."""

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
                    record(
                        RunActivity(
                            phase=RunActivityPhase.LLM_THINKING.value,
                            step=self._step,
                            detail=f"{self._model} 推理中…",
                            seq=self._seq,
                        )
                    )
                    if self._on_idle is not None:
                        self._on_idle(idle_s, self._seq)
                    self._seq += 1
        except asyncio.CancelledError:
            raise
