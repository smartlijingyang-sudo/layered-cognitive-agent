"""Routine tick driver: failure isolation, retry backoff, dead letters (ADR-0263 T5/C5).

The scheduler (T1--T4) decides *whether* a routine may run; the driver runs the
tick. Per routine, in order:

1. dead-lettered  -> skipped as ``DEAD_LETTERED`` (never executed again);
2. inside a failure backoff window -> skipped as ``SKIPPED(NOT_DUE)``;
3. scheduler verdict denies -> ``SKIPPED(<reason>)``;
4. otherwise: reclaim stale lock (traced), acquire the lock, run the executor
   under a heartbeat refresher (long holds are never reclaimed mid-flight),
   release the lock.

Failure semantics (ADR-0263 §9 ruling 3, pinned by the acceptance tests):
retry up to 3 attempts with 1min/5min/15min backoff; the 3rd failure moves the
routine to a dead letter queryable for 7 days. Every failure emits
``routine.failed.v1``; the crossing failure also emits
``routine.dead_lettered.v1``. An executor exception never kills the tick —
it becomes a ``FAILED`` result and the driver continues with the next routine.

Design points settled here (tests-lane open design points):
- failure-state / dead-letter persistence: sidecar JSON files under the
  repository storage dir (``failures/`` and ``dead_letters/``), mirroring the
  existing ``triggers/`` precedent; atomic tmp+replace writes; a fresh driver
  over the same dirs sees the same state (restart-safe, no in-memory dict).
- ``record_triggered`` is called only on successful execution: a failed attempt
  is not a completed trigger — recording it would close the trigger window and
  starve the C5 retry/backoff semantics.
- expired dead letters are pruned lazily (on read): "kept 7 days" is enforced,
  and the routine becomes schedulable again afterwards.
- ``on_event`` is the event sink for journal/spine wiring; event names:
  ``routine.failed.v1`` / ``routine.dead_lettered.v1`` /
  ``routine.lock.stale_reclaimed.v1`` / ``routine.skipped.v1`` (C3: every SKIP
  leaves a trace).
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from lca.application.routine.locks import RoutineFileLock
from lca.application.routine.scheduler import RoutineSchedulerService
from lca.application.routine.verdicts import SkipReason
from lca.contracts.models.routine.models import RoutineSpec
from lca.domain.routine.repository import JsonRoutineRepository

#: ADR-0263 §9 ruling 3: 3 attempts, backoff 1min/5min/15min.
#: attempts=1 fails -> next retry after index 0 (60s); attempts=2 fails ->
#: index 1 (300s); attempts=3 fails -> dead letter, no further backoff.
RETRY_BACKOFFS_S = (60.0, 300.0, 900.0)
MAX_ATTEMPTS = 3

#: ADR-0263 §9 ruling 3: dead letters stay queryable for 7 days.
DEAD_LETTER_TTL_S = 7 * 24 * 3600

#: Event names emitted through ``on_event`` (ADR-0263 C2/C3/C5: never silent).
EVENT_FAILED = "routine.failed.v1"
EVENT_DEAD_LETTERED = "routine.dead_lettered.v1"
EVENT_LOCK_STALE_RECLAIMED = "routine.lock.stale_reclaimed.v1"
EVENT_SKIPPED = "routine.skipped.v1"

#: Heartbeat refresh cadence during executor runs: a quarter of the stale
#: threshold, capped so production's 90min threshold doesn't refresh hourly.
_HEARTBEAT_PERIOD_CAP_S = 60.0


class TickOutcome(StrEnum):
    """What one routine's tick produced (ADR-0263 T5)."""

    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True)
class TickResult:
    """Per-routine outcome of one ``tick_once`` pass."""

    routine_id: str
    outcome: TickOutcome
    skip_reason: SkipReason | None = None


@dataclass(frozen=True)
class TickReport:
    """Full result of one ``tick_once`` pass, in input order."""

    results: tuple[TickResult, ...]


@dataclass(frozen=True)
class FailureState:
    """Persisted consecutive-failure state of one routine (C5)."""

    routine_id: str
    attempts: int
    last_error: str
    last_failed_at_s: float
    next_retry_at_s: float


@dataclass(frozen=True)
class DeadLetter:
    """A routine that exhausted its retries (C5, kept 7 days)."""

    routine_id: str
    attempts: int
    last_error: str
    dead_at_s: float
    expires_at_s: float


class _HeartbeatRefresher:
    """Daemon thread keeping the held lock's heartbeat fresh during execution.

    Without this, a long-running executor would go stale and a concurrent
    tick could reclaim its lock mid-flight (ADR-0263 T5f pins the guarantee).
    """

    def __init__(self, lock: RoutineFileLock, stale_after_s: float) -> None:
        self._lock = lock
        self._period_s = max(min(stale_after_s / 4, _HEARTBEAT_PERIOD_CAP_S), 1e-3)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> _HeartbeatRefresher:
        self._thread = threading.Thread(target=self._run, name="routine-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self._period_s * 2, 0.5))

    def _run(self) -> None:
        while not self._stop.wait(self._period_s):
            with contextlib.suppress(Exception):
                self._lock.refresh_heartbeat()


class RoutineTickDriver:
    """Execute one tick over routines with C5 failure isolation (ADR-0263 §10).

    The driver is stateless across ticks except for the on-disk sidecars:
    a fresh instance over the same repository/lock dirs sees the same failure
    counts and dead letters, so a process restart never loses them.
    """

    def __init__(
        self,
        *,
        scheduler: RoutineSchedulerService,
        repository: JsonRoutineRepository,
        lock_dir: str | Path,
        stale_after_s: float | None = None,
        clock: Callable[[], float] = time.time,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._repository = repository
        self._lock_dir = Path(lock_dir).expanduser().resolve()
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._stale_after_s = stale_after_s
        self._clock = clock
        self._on_event = on_event
        self._failures_dir = repository.storage_dir / "failures"
        self._dead_dir = repository.storage_dir / "dead_letters"

    # -- public API ------------------------------------------------------

    def tick_once(
        self,
        routines: list[RoutineSpec],
        executor: Callable[[RoutineSpec], None],
    ) -> TickReport:
        """Run one tick over ``routines`` in order.

        Never raises for executor failures: a raising executor becomes a
        ``FAILED`` result and the tick continues with the next routine (T5).
        """
        return TickReport(results=tuple(self._tick_one(spec, executor) for spec in routines))

    def get_failure_state(self, routine_id: str) -> FailureState | None:
        """Read the persisted failure state; ``None`` when never failed (or cleared)."""
        data = self._read_json(self._failures_dir / f"{routine_id}.json")
        if data is None:
            return None
        try:
            return FailureState(
                routine_id=str(data["routine_id"]),
                attempts=int(data["attempts"]),
                last_error=str(data["last_error"]),
                last_failed_at_s=float(data["last_failed_at_s"]),
                next_retry_at_s=float(data["next_retry_at_s"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def list_dead(self) -> list[DeadLetter]:
        """List dead letters; lazily prunes entries past their 7-day TTL."""
        now = self._clock()
        letters: list[DeadLetter] = []
        if not self._dead_dir.is_dir():
            return letters
        for path in sorted(self._dead_dir.glob("*.json")):
            letter = self._read_dead(path)
            if letter is None:
                continue
            if letter.expires_at_s <= now:
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            letters.append(letter)
        return letters

    # -- one routine -----------------------------------------------------

    def _tick_one(self, spec: RoutineSpec, executor: Callable[[RoutineSpec], None]) -> TickResult:
        now = self._clock()

        if self._load_dead(spec.id) is not None:
            return TickResult(spec.id, TickOutcome.DEAD_LETTERED)

        state = self.get_failure_state(spec.id)
        if state is not None and now < state.next_retry_at_s:
            # Inside the C5 backoff window: "not yet time for the next attempt".
            self._emit_skipped(spec.id, SkipReason.NOT_DUE, now)
            return TickResult(spec.id, TickOutcome.SKIPPED, SkipReason.NOT_DUE)

        decision = self._scheduler.evaluate(spec.id)
        if not decision.allowed and decision.skip_reason is not None:
            self._emit_skipped(spec.id, decision.skip_reason, now)
            return TickResult(spec.id, TickOutcome.SKIPPED, decision.skip_reason)
        # A skip verdict always names its reason (TriggerDecision.__post_init__
        # rejects allowed=False with skip_reason=None), so reaching here means
        # the routine may run.

        lock = RoutineFileLock(
            self._lock_dir,
            spec.id,
            stale_after_s=self._stale_after_s,
            routine_interval_s=spec.interval_s,
        )
        reclaimed = lock.reclaim_stale()
        if reclaimed is not None:
            self._emit(
                EVENT_LOCK_STALE_RECLAIMED,
                {
                    "routine_id": spec.id,
                    "previous_owner": reclaimed.previous_owner,
                    "held_ms": reclaimed.held_ms,
                },
            )
        if not lock.acquire():
            # Lost the race after evaluate(): someone else is running it.
            self._emit_skipped(spec.id, SkipReason.ALREADY_RUNNING, now)
            return TickResult(spec.id, TickOutcome.SKIPPED, SkipReason.ALREADY_RUNNING)

        try:
            with _HeartbeatRefresher(lock, lock.stale_after_s):
                executor(spec)
        except Exception as exc:
            return self._record_failure(spec, state, exc)
        finally:
            lock.release()

        self._clear_failure_state(spec.id)
        # Only a completed execution counts as a trigger: a failed attempt must
        # not close the trigger window, or C5 retries would starve as NOT_DUE.
        self._scheduler.record_triggered(spec.id, trigger_source="tick")
        return TickResult(spec.id, TickOutcome.EXECUTED)

    def _record_failure(
        self, spec: RoutineSpec, state: FailureState | None, exc: BaseException
    ) -> TickResult:
        now = self._clock()
        attempts = (state.attempts if state is not None else 0) + 1
        error = f"{type(exc).__name__}: {exc}"
        self._emit(
            EVENT_FAILED,
            {"routine_id": spec.id, "error": error, "retry_count": attempts},
        )
        if attempts >= MAX_ATTEMPTS:
            letter = DeadLetter(
                routine_id=spec.id,
                attempts=attempts,
                last_error=error,
                dead_at_s=now,
                expires_at_s=now + DEAD_LETTER_TTL_S,
            )
            self._write_json(self._dead_dir / f"{spec.id}.json", asdict(letter))
            self._clear_failure_state(spec.id)
            self._emit(
                EVENT_DEAD_LETTERED,
                {"routine_id": spec.id, "attempts": attempts, "last_error": error},
            )
            # The tick executed and failed; death is a state transition on top,
            # observable via list_dead() / the dead_lettered event.
            return TickResult(spec.id, TickOutcome.FAILED)
        backoff_s = RETRY_BACKOFFS_S[attempts - 1]
        self._write_json(
            self._failures_dir / f"{spec.id}.json",
            {
                "routine_id": spec.id,
                "attempts": attempts,
                "last_error": error,
                "last_failed_at_s": now,
                "next_retry_at_s": now + backoff_s,
            },
        )
        return TickResult(spec.id, TickOutcome.FAILED)

    # -- sidecars --------------------------------------------------------

    def _load_dead(self, routine_id: str) -> DeadLetter | None:
        """Read one dead letter; prunes it when past its TTL."""
        path = self._dead_dir / f"{routine_id}.json"
        letter = self._read_dead(path)
        if letter is not None and letter.expires_at_s <= self._clock():
            with contextlib.suppress(OSError):
                path.unlink()
            return None
        return letter

    def _read_dead(self, path: Path) -> DeadLetter | None:
        data = self._read_json(path)
        if data is None:
            return None
        try:
            return DeadLetter(
                routine_id=str(data["routine_id"]),
                attempts=int(data["attempts"]),
                last_error=str(data["last_error"]),
                dead_at_s=float(data["dead_at_s"]),
                expires_at_s=float(data["expires_at_s"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _clear_failure_state(self, routine_id: str) -> None:
        with contextlib.suppress(OSError):
            (self._failures_dir / f"{routine_id}.json").unlink()

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".tmp_{path.name}"
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(path)

    # -- events ----------------------------------------------------------

    def _emit(self, name: str, payload: dict) -> None:
        if self._on_event is not None:
            self._on_event(name, payload)

    def _emit_skipped(self, routine_id: str, reason: SkipReason, now: float) -> None:
        # ADR-0263 C3: every SKIP leaves a trace — why a routine did not run
        # must be queryable.
        self._emit(
            EVENT_SKIPPED,
            {
                "routine_id": routine_id,
                "skip_reason": reason.value,
                "evaluated_at_s": now,
            },
        )


__all__ = [
    "DEAD_LETTER_TTL_S",
    "EVENT_DEAD_LETTERED",
    "EVENT_FAILED",
    "EVENT_LOCK_STALE_RECLAIMED",
    "EVENT_SKIPPED",
    "MAX_ATTEMPTS",
    "RETRY_BACKOFFS_S",
    "DeadLetter",
    "FailureState",
    "RoutineTickDriver",
    "TickOutcome",
    "TickReport",
    "TickResult",
]
