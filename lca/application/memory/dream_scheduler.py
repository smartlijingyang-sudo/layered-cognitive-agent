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
import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from lca.application.routine.locks import RoutineFileLock
from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.edit import StaleSnapshotOperationError
from lca.infrastructure.memory.dream import DreamReport, run_dream

logger = logging.getLogger(__name__)

_Backfill = Callable[[str, list[MemoryRecord]], object]
_Render = Callable[[Sequence[MemoryRecord]], str]
DreamFn = Callable[..., DreamReport | None]
EvidenceWriter = Callable[[Path, DreamReport | None, int], object]

_ROUTINE_ID = "memory_dream"

#: Reclaim bound for one home's dream lock. Deliberately not derived from
#: ``tick_seconds``: the interval says how often we sweep, this says how long one
#: pass may hold the lock before another process may assume the holder died.
#: A measured pass costs 11-30ms per home, so 900s is roughly 30,000x the worst
#: measured case and still covers a pathological FTS index rebuild, while a
#: genuinely dead lock costs one home at most three 300s ticks instead of never
#: dreaming again, which is what the reclaim is for.
_STALE_AFTER_S = 900.0

#: A pass that holds the lock past a tenth of the reclaim bound gets a WARNING,
#: so the bound stays observable instead of assumed.
_SLOW_PASS_MS = _STALE_AFTER_S * 1000 / 10


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
        return await asyncio.to_thread(self._locked_pass, home, now_ms)

    def _locked_pass(self, home: Path, now_ms: int) -> DreamReport | None:
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
            stale_after_s=_STALE_AFTER_S,
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
        held_from_ms = self._now_ms()
        try:
            render, backfill = (
                self._callbacks(home) if self._callbacks is not None else (None, None)
            )
            report = self._run_dream(home, now_ms=now_ms, backfill=backfill, render=render)
            self._record_evidence(home, report, now_ms)
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
            held_ms = self._now_ms() - held_from_ms
            if held_ms > _SLOW_PASS_MS:
                logger.warning(
                    "dream pass overran a tenth of the reclaim bound: home=%s held_ms=%d",
                    home.name,
                    held_ms,
                )

    def _record_evidence(self, home: Path, report: DreamReport | None, now_ms: int) -> None:
        """Write the run artifact, inside the lock, without owning the report.

        ``run_dream`` has already committed its promotions when this runs, and
        the artifact is a rebuildable projection of them, so no writer failure
        may turn a successful consolidation into a reported loss. The handler is
        ``Exception`` rather than ``OSError`` because the writer is an injected
        seam whose failure modes this module does not own; ``BaseException``
        still propagates, so dispose-by-cancel is unaffected.
        """
        if self._evidence_writer is None:
            return
        try:
            self._evidence_writer(home, report, now_ms)
        except Exception:
            logger.exception("dream evidence write failed: home=%s", home.name)


_EVIDENCE_RELATIVE = "dreams/last_run.json"


def _changed(report: DreamReport) -> bool:
    """True when this pass moved a fact or re-projected the profile.

    Deliberately narrower than "the pass did work". ``synthesis_written`` is
    hardcoded ``True`` (``dream.py:214``), ``promoted`` repeats every past
    promotion because it is appended before the ``_already_active`` skip
    (``dream.py:241``), ``trail_facts`` counts the whole trail corpus rather than
    what is new in it, and ``people_indexed``/``groups_indexed``/
    ``index_documents`` count rebuilds of artifacts every pass rewrites
    unconditionally. Only a written semantic row and a USER.md whose rendering
    differed from what is on disk are content differences.
    """
    return bool(report.upserted or report.user_md_written)


def write_dream_evidence(home: Path, report: DreamReport | None, now_ms: int) -> Path | None:
    """Record the pass under ``{home}/dreams/last_run.json``.

    A pass that changed nothing leaves the previous evidence in place, so the
    file's mtime stays a truthful "last time memory moved" marker and a
    minutes-level cadence does not churn it. A home with no artifact yet always
    gets one, so the file's absence means the sweep never reached that home.

    The write goes through the home's atomic replace, because a half-written
    artifact is worse than a stale one: ``is_file()`` would then protect the
    corrupt file from being overwritten by every later idle pass.
    """
    path = home / _EVIDENCE_RELATIVE
    if report is None or (not _changed(report) and path.is_file()):
        return None
    payload = {
        "now_ms": now_ms,
        "upserted": report.upserted,
        "promoted": report.promoted,
        "user_md_written": report.user_md_written,
        "synthesis_written": report.synthesis_written,
        "trail_facts": report.trail_facts,
        "index_documents": report.index_documents,
    }
    DiskFileStore(home).atomic_replace(
        _EVIDENCE_RELATIVE, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return path
