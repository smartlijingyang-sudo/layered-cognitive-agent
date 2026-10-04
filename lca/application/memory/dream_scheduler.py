"""Periodic sweep that runs the offline memory consolidation per assistant home.

The loop keeps its own interval bookkeeping. It does not route through
``next_run``: that function decides ``due`` by exact ``datetime`` equality
including microseconds, which a discrete tick sampling a continuous clock never
satisfies, so every periodic schedule kind is unreachable there.

``run_dream`` is synchronous and does file I/O, so the sweep dispatches the
whole locked pass, lock files and evidence write included, to an executor
thread. The kernel process serves HTTP on the same loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from lca.application.routine.locks import RoutineFileLock
from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.contextfiles.domain.edit import StaleSnapshotOperationError
from lca.infrastructure.memory.dream import DreamReport, run_dream

logger = logging.getLogger(__name__)

_Backfill = Callable[[str, list[MemoryRecord]], object]
_Render = Callable[[Sequence[MemoryRecord]], str]
DreamFn = Callable[..., DreamReport | None]
EvidenceWriter = Callable[[Path, DreamReport | None, int], object]

_ROUTINE_ID = "memory_dream"


def _dream_lock_id(home: Path) -> str:
    """Lock id for one home. Keyed on the path, since two homes can share a basename."""
    return f"{_ROUTINE_ID}:{sha256_hex(str(home).encode(), length=16)}"


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
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=float(self._tick_seconds))

    async def sweep_once(self) -> tuple[DreamReport | None, ...]:
        """Run one pass over every home. Returns one report per home, None when skipped."""
        now = self._now_ms()
        if self._next_due_ms is not None and now < self._next_due_ms:
            return ()
        self._next_due_ms = now + self._tick_seconds * 1000
        reports: list[DreamReport | None] = []
        for home in self._homes():
            try:
                reports.append(await self._run_home(home, now))
            except Exception:
                logger.exception("dream pass raised: %s", home.name)
                reports.append(None)
        return tuple(reports)

    async def _run_home(self, home: Path, now_ms: int) -> DreamReport | None:
        render, backfill = self._callbacks(home) if self._callbacks is not None else (None, None)
        return await asyncio.to_thread(
            self._locked_pass, home, now_ms, render=render, backfill=backfill
        )

    def _locked_pass(
        self,
        home: Path,
        now_ms: int,
        *,
        render: _Render | None,
        backfill: _Backfill | None,
    ) -> DreamReport | None:
        """One dream pass under the home's lock, on an executor thread.

        The lock lives as long as this function rather than as long as the
        await, because ``asyncio.to_thread`` cannot interrupt a running
        executor thread: releasing on cancellation would leave ``run_dream``
        executing while a second acquirer walks in. Reclaiming before the
        acquire is what keeps a holder killed mid-dream from taking the home
        out of the sweep for good.
        """
        lock = RoutineFileLock(
            self._lock_dir,
            _dream_lock_id(home),
            routine_interval_s=float(self._tick_seconds),
        )
        reclaimed = lock.reclaim_stale()
        if reclaimed is not None:
            logger.warning(
                "dream reclaimed a stale lock: home=%s previous_owner=%s held_ms=%d",
                home.name,
                reclaimed.previous_owner,
                reclaimed.held_ms,
            )
        if not lock.acquire():
            logger.info("dream skipped, home locked: %s", home.name)
            return None
        try:
            report = self._run_dream(home, now_ms=now_ms, backfill=backfill, render=render)
            if self._evidence_writer is not None:
                self._evidence_writer(home, report, now_ms)
            return report
        except StaleSnapshotOperationError:
            # An online memory tool rewrote semantic.json mid-pass. The next
            # sweep re-reads from disk, so abandoning this pass loses nothing.
            logger.warning("dream pass abandoned, semantic.json moved: %s", home.name)
            return None
        except OSError:
            logger.exception("dream pass failed on I/O: %s", home.name)
            return None
        finally:
            if not lock.release():
                logger.warning("dream lock release failed: %s", home.name)
