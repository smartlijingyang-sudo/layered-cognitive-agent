"""Periodic sweep that runs the offline memory consolidation per assistant home.

The loop keeps its own interval bookkeeping. It does not route through
``next_run``: that function decides ``due`` by exact ``datetime`` equality
including microseconds, which a discrete tick sampling a continuous clock never
satisfies, so every periodic schedule kind is unreachable there.

``run_dream`` is synchronous and does file I/O, so the sweep dispatches it off
the event loop. The kernel process serves HTTP on the same loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from lca.application.routine.locks import RoutineFileLock
from lca.infrastructure.memory.dream import DreamReport, run_dream

logger = logging.getLogger(__name__)

_Backfill = Callable[[str, list], object]
_Render = Callable[[Sequence], str]
DreamFn = Callable[..., DreamReport]
EvidenceWriter = Callable[[Path, "DreamReport | None", int], object]

_ROUTINE_ID = "memory_dream"


class DreamScheduler:
    """Sweep every assistant home once per ``tick_seconds``."""

    def __init__(
        self,
        homes: Callable[[], Sequence[Path]],
        *,
        lock_dir: Path,
        tick_seconds: int,
        now_ms: Callable[[], int],
        run_dream_fn: DreamFn = run_dream,
        evidence_writer: EvidenceWriter | None = None,
        callbacks: Callable[[Path], tuple[_Render | None, _Backfill | None]] | None = None,
    ) -> None:
        self._homes = homes
        self._lock_dir = Path(lock_dir)
        self._tick_seconds = tick_seconds
        self._now_ms = now_ms
        self._run_dream = run_dream_fn
        self._evidence_writer = evidence_writer
        self._callbacks = callbacks
        self._stop = asyncio.Event()
        self._next_due_ms: int | None = None

    def stop(self) -> None:
        """Signal the loop to exit at its next check. Idempotent."""
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self.sweep_once()
            except Exception:
                logger.exception("dream sweep failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=float(self._tick_seconds))
            except TimeoutError:
                continue

    async def sweep_once(self) -> tuple[DreamReport | None, ...]:
        """Run one pass over every home. Returns one report per home, None when skipped."""
        now = self._now_ms()
        if self._next_due_ms is not None and now < self._next_due_ms:
            return ()
        self._next_due_ms = now + self._tick_seconds * 1000
        reports: list[DreamReport | None] = []
        for home in self._homes():
            reports.append(await self._run_home(Path(home), now))
        return tuple(reports)

    async def _run_home(self, home: Path, now_ms: int) -> DreamReport | None:
        lock = RoutineFileLock(
            self._lock_dir,
            f"{_ROUTINE_ID}:{home.name}",
            routine_interval_s=float(self._tick_seconds),
        )
        if not lock.acquire():
            logger.info("dream skipped, home locked: %s", home.name)
            return None
        try:
            render, backfill = (
                self._callbacks(home) if self._callbacks is not None else (None, None)
            )
            report = await asyncio.to_thread(
                self._run_dream,
                home,
                now_ms=now_ms,
                backfill=backfill,
                render=render,
            )
        finally:
            lock.release()
        if self._evidence_writer is not None:
            self._evidence_writer(home, report, now_ms)
        return report
