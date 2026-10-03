"""Routine mutual-exclusion file lock with stale self-healing (ADR-0263 C1/C2).

Production precedent: the three iter lanes' startup lock stanza
(lock dir + ``age < threshold -> busy -> skip`` + stale reclaim + hold till
round end + release). This module contracts that pattern into LCA routine
scheduling semantics.

Lock file: ``<lock_dir>/<routine_id>.lock``, JSON
``{"owner": str, "heartbeat_ms": int}``. The on-disk format is part of the
contract (ADR-0263 T2 simulates kill -9 by writing a stale lock file directly).

Intended tick-driver flow (T5, ADR-0263 §10 — not this module's job):
``reclaim_stale()`` -> journal the ReclaimInfo if any -> ``acquire()`` ->
run -> ``release()``. ``acquire()`` deliberately does NOT auto-reclaim:
a silent reclaim would drop the ReclaimInfo trace, and ADR-0263 C2 requires
reclaim to leave a trace, never be silent.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from lca.contracts.atoms.ids.ids import utc_now_ms

#: Absolute cap for the stale threshold (ADR-0263 §9 ruling 2):
#: never wait longer than 90 minutes to reclaim a dead holder's lock,
#: no matter how long the routine interval is.
STALE_AFTER_CAP_S = 5_400

#: Fallback stale threshold for routines that declare no interval
#: (mirrors the three production cron lanes: hourly cadence, 5400s stale).
DEFAULT_STALE_AFTER_S = 5_400


@dataclass(frozen=True)
class ReclaimInfo:
    """Trace left by a stale-lock reclaim (ADR-0263 C2: never silent)."""

    previous_owner: str
    held_ms: int
    reclaimed_at_ms: int


class RoutineFileLock:
    """Single-instance mutual exclusion for one routine (ADR-0263 C1).

    ``acquire()`` is atomic (O_CREAT|O_EXCL): a second concurrent acquirer
    gets ``False`` — no queueing, no waiting (T1). A lock whose heartbeat
    is older than the stale threshold is considered dead; ``reclaim_stale()``
    removes it and returns the trace, ``is_locked()`` reads it as unlocked
    so a dead holder never blocks verdicts forever.
    """

    def __init__(
        self,
        lock_dir: str | Path,
        routine_id: str,
        stale_after_s: float | None = None,
        routine_interval_s: float | None = None,
    ) -> None:
        self._lock_dir = Path(lock_dir).expanduser().resolve()
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._lock_dir / f"{routine_id}.lock"
        self._owner = f"pid:{os.getpid()}"
        self._stale_after_s = self._resolve_stale_after_s(stale_after_s, routine_interval_s)

    @staticmethod
    def _resolve_stale_after_s(
        stale_after_s: float | None, routine_interval_s: float | None
    ) -> float:
        if stale_after_s is not None:
            return stale_after_s
        if routine_interval_s is not None:
            # ADR-0263 §9 ruling 2: default 2x routine interval, hard cap 90min.
            return min(2 * routine_interval_s, STALE_AFTER_CAP_S)
        return DEFAULT_STALE_AFTER_S

    @property
    def stale_after_s(self) -> float:
        """Effective stale threshold in seconds."""
        return self._stale_after_s

    def acquire(self) -> bool:
        """Take the lock. ``True`` on success, ``False`` if already held.

        Does not auto-reclaim a stale lock: call ``reclaim_stale()`` first
        so the reclaim leaves its trace (ADR-0263 C2).
        """
        payload = {"owner": self._owner, "heartbeat_ms": utc_now_ms()}
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
        except OSError:
            with contextlib.suppress(OSError):
                self._path.unlink(missing_ok=True)
            return False
        return True

    def release(self) -> bool:
        """Release the lock. Only the owner can release; never touches
        another holder's lock file. ``True`` if we released it."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if data.get("owner") != self._owner:
            return False
        try:
            self._path.unlink()
        except OSError:
            return False
        return True

    def is_locked(self) -> bool:
        """Non-mutating probe: a fresh lock file exists.

        A stale lock file reads as *unlocked* — the holder is presumed dead
        and the tick driver reclaims it explicitly before acquiring.
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            heartbeat_ms = int(data["heartbeat_ms"])
        except (OSError, ValueError, KeyError, TypeError):
            return False
        return utc_now_ms() - heartbeat_ms < self._stale_after_s * 1000

    def reclaim_stale(self) -> ReclaimInfo | None:
        """Remove a dead holder's lock file and return the trace.

        ``None`` when there is no lock file or the lock is still fresh.
        A corrupt lock file is treated as stale (it can never become fresh
        again, so reclaiming is the only self-healing move).
        """
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data = json.loads(raw)
            heartbeat_ms = int(data["heartbeat_ms"])
            owner = str(data.get("owner", "unknown"))
        except (ValueError, KeyError, TypeError):
            heartbeat_ms = 0
            owner = "unknown"
        now_ms = utc_now_ms()
        if now_ms - heartbeat_ms < self._stale_after_s * 1000:
            return None
        try:
            self._path.unlink()
        except OSError:
            return None  # someone else reclaimed it first
        return ReclaimInfo(
            previous_owner=owner,
            held_ms=now_ms - heartbeat_ms,
            reclaimed_at_ms=now_ms,
        )

    def refresh_heartbeat(self) -> None:
        """Refresh the held lock's heartbeat to the current time (ADR-0263 T5f).

        Best-effort: no-op when the lock file is missing, corrupt, or owned by
        someone else — the tick driver must never touch another holder's lock.
        Called by the tick driver's heartbeat thread so a long-running
        executor is not reclaimed as stale mid-flight.
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("owner") != self._owner:
            return
        data["heartbeat_ms"] = utc_now_ms()
        try:
            self._path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            return


__all__ = [
    "DEFAULT_STALE_AFTER_S",
    "STALE_AFTER_CAP_S",
    "ReclaimInfo",
    "RoutineFileLock",
]
