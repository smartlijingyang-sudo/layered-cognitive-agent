import asyncio
import json
import logging
import threading
from pathlib import Path

import pytest

from lca.application.memory.dream_scheduler import (
    DreamFn,
    DreamScheduler,
    _Backfill,
    _dream_lock_id,
    _Render,
)
from lca.application.routine.locks import RoutineFileLock
from lca.contracts.atoms.ids.ids import utc_now_ms
from lca.infrastructure.memory.contextfiles.domain.edit import StaleSnapshotOperationError
from lca.infrastructure.memory.dream import DreamReport

EvidenceCall = tuple[Path, DreamReport | None, int]


def _report(**overrides) -> DreamReport:
    base = {
        "promoted": (),
        "upserted": 0,
        "preimage": None,
        "user_md_written": False,
        "trail_facts": 0,
        "people_indexed": 0,
        "groups_indexed": 0,
        "synthesis_written": False,
        "synthesis_path": "",
        "synthesis_assertions": 0,
        "index_documents": 0,
    }
    base.update(overrides)
    return DreamReport(**base)


@pytest.fixture
def clock() -> list[int]:
    return [1_791_121_000_000]


def _scheduler(
    tmp_path: Path,
    homes: list[Path],
    clock: list[int],
    calls: list[Path],
    evidence: list[EvidenceCall] | None = None,
    run_dream_fn: DreamFn | None = None,
) -> DreamScheduler:
    recorded: list[EvidenceCall] = [] if evidence is None else evidence

    def fake_run_dream(
        home: Path,
        *,
        now_ms: int,
        backfill: _Backfill | None,
        render: _Render | None,
    ) -> DreamReport:
        assert now_ms == clock[0], "the injected clock is the value that reaches run_dream"
        calls.append(home)
        return _report()

    def write_evidence(home: Path, report: DreamReport | None, now_ms: int) -> None:
        recorded.append((home, report, now_ms))

    return DreamScheduler(
        homes=lambda: homes,
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=fake_run_dream if run_dream_fn is None else run_dream_fn,
        evidence_writer=write_evidence,
    )


def _home_lock(lock_dir: Path, home: Path) -> RoutineFileLock:
    return RoutineFileLock(lock_dir, _dream_lock_id(home))


def _colliding(
    home: Path, *, now_ms: int, backfill: _Backfill | None, render: _Render | None
) -> DreamReport:
    raise StaleSnapshotOperationError(f"{home.name}: semantic.json changed during edit")


async def test_sweep_once_visits_every_home(tmp_path: Path, clock: list[int]) -> None:
    homes = [tmp_path / "a", tmp_path / "b"]
    calls: list[Path] = []
    evidence: list[EvidenceCall] = []
    scheduler = _scheduler(tmp_path, homes, clock, calls, evidence)

    reports = await scheduler.sweep_once()

    assert calls == homes
    assert reports == (_report(), _report())
    assert evidence == [(homes[0], _report(), clock[0]), (homes[1], _report(), clock[0])]


async def test_interval_skips_a_sweep_that_is_not_due_yet(tmp_path: Path, clock: list[int]) -> None:
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [tmp_path / "a"], clock, calls)

    assert await scheduler.sweep_once() == (_report(),)
    assert await scheduler.sweep_once() == (), "a sweep inside the interval reports nothing"

    assert calls == [tmp_path / "a"], "a sweep inside the interval never reaches run_dream"

    clock[0] += 300_000
    await scheduler.sweep_once()

    assert calls == [tmp_path / "a", tmp_path / "a"]


async def test_run_forever_sweeps_then_exits_on_stop(tmp_path: Path, clock: list[int]) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    swept = asyncio.Event()

    def homes() -> list[Path]:
        swept.set()
        return [home]

    def fake_run_dream(
        seen_home: Path,
        *,
        now_ms: int,
        backfill: _Backfill | None,
        render: _Render | None,
    ) -> DreamReport:
        calls.append(seen_home)
        return _report()

    scheduler = DreamScheduler(
        homes=homes,
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=fake_run_dream,
    )

    loop = asyncio.create_task(scheduler.run_forever())
    await asyncio.wait_for(swept.wait(), timeout=5)
    scheduler.stop()
    await asyncio.wait_for(loop, timeout=5)

    assert calls == [home], "the loop swept once and returned once stop() was called"


async def test_run_forever_keeps_ticking_after_the_interval(
    tmp_path: Path, clock: list[int]
) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    sweeps = 0
    scheduler: DreamScheduler | None = None

    def homes() -> list[Path]:
        nonlocal sweeps
        sweeps += 1
        if sweeps == 2 and scheduler is not None:
            scheduler.stop()
        return [home]

    def fake_run_dream(
        seen_home: Path,
        *,
        now_ms: int,
        backfill: _Backfill | None,
        render: _Render | None,
    ) -> DreamReport:
        calls.append(seen_home)
        return _report()

    scheduler = DreamScheduler(
        homes=homes,
        lock_dir=tmp_path / "locks",
        tick_seconds=0,
        now_ms=lambda: clock[0],
        run_dream_fn=fake_run_dream,
    )

    await asyncio.wait_for(scheduler.run_forever(), timeout=5)

    assert sweeps == 2, "an elapsed interval ticks again instead of killing the loop"
    assert calls == [home, home]


async def test_stop_before_start_exits_without_sweeping(tmp_path: Path, clock: list[int]) -> None:
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [tmp_path / "a"], clock, calls)

    scheduler.stop()
    scheduler.stop()
    await asyncio.wait_for(scheduler.run_forever(), timeout=5)

    assert calls == [], "a stopped loop never sweeps"


async def test_a_held_lock_skips_the_home(tmp_path: Path, clock: list[int]) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [home], clock, calls)
    holder = _home_lock(tmp_path / "locks", home)
    assert holder.acquire() is True

    reports = await scheduler.sweep_once()

    assert calls == [], "a home another holder owns is skipped, never run unlocked"
    assert reports == (None,)
    holder.release()


async def test_a_stale_lock_from_a_dead_pid_is_reclaimed(
    tmp_path: Path, clock: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [home], clock, calls)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    # 660s old against a 600s threshold: min(2 * tick_seconds, STALE_AFTER_CAP_S).
    stale = lock_dir / f"{_dream_lock_id(home)}.lock"
    stale.write_text(
        json.dumps({"owner": "pid:999999", "heartbeat_ms": utc_now_ms() - 660_000}),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        reports = await scheduler.sweep_once()

    assert calls == [home], "a dead holder's lock is reclaimed instead of skipping the home"
    assert reports == (_report(),)
    assert any(
        "previous_owner=pid:999999" in record.message and "held_ms=" in record.message
        for record in caplog.records
    ), "a reclaim leaves the trace ADR-0263 C2 requires"
    assert not stale.exists(), "the reclaimed lock is released when the pass ends"


async def test_a_write_collision_is_contained_not_raised(
    tmp_path: Path, clock: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [tmp_path / "a"], clock, calls, run_dream_fn=_colliding)

    with caplog.at_level(logging.WARNING):
        reports = await scheduler.sweep_once()

    assert reports == (None,), "a collision abandons this pass and reports nothing"
    assert any("dream pass abandoned" in record.message for record in caplog.records), (
        "a collision is diagnosed as a collision, not as an unclassified pass failure"
    )


async def test_the_lock_is_released_after_a_collision(tmp_path: Path, clock: list[int]) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [home], clock, calls, run_dream_fn=_colliding)

    await scheduler.sweep_once()

    after = _home_lock(tmp_path / "locks", home)
    assert after.acquire() is True, "a collided pass must not strand its lock"
    after.release()


async def test_an_io_failure_is_contained_and_diagnosed(
    tmp_path: Path, clock: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []

    def unreadable(
        seen: Path, *, now_ms: int, backfill: _Backfill | None, render: _Render | None
    ) -> DreamReport:
        calls.append(seen)
        raise FileNotFoundError(f"{seen}/memory/semantic.json")

    scheduler = _scheduler(tmp_path, [home], clock, calls, run_dream_fn=unreadable)

    with caplog.at_level(logging.WARNING):
        reports = await scheduler.sweep_once()

    assert reports == (None,)
    assert any("dream pass failed on I/O" in record.message for record in caplog.records), (
        "an I/O failure is diagnosed as I/O, not left to the sweep's catch-all"
    )
    after = _home_lock(tmp_path / "locks", home)
    assert after.acquire() is True, "a failed pass must not strand its lock"
    after.release()


async def test_a_release_that_returns_false_is_logged(
    tmp_path: Path, clock: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "a"
    calls: list[Path] = []
    lock_path = tmp_path / "locks" / f"{_dream_lock_id(home)}.lock"

    def losing_the_lock(
        seen: Path, *, now_ms: int, backfill: _Backfill | None, render: _Render | None
    ) -> DreamReport:
        # A pass that outlives its stale threshold is reclaimed by another kernel.
        lock_path.unlink()
        calls.append(seen)
        return _report()

    scheduler = _scheduler(tmp_path, [home], clock, calls, run_dream_fn=losing_the_lock)

    with caplog.at_level(logging.WARNING):
        reports = await scheduler.sweep_once()

    assert calls == [home]
    assert reports == (_report(),), "losing the lock mid-pass does not discard the report"
    assert any("dream lock release failed" in record.message for record in caplog.records)


async def test_one_raising_home_does_not_stop_the_sweep(tmp_path: Path, clock: list[int]) -> None:
    bad = tmp_path / "a"
    good = tmp_path / "b"
    calls: list[Path] = []

    def flaky(
        home: Path, *, now_ms: int, backfill: _Backfill | None, render: _Render | None
    ) -> DreamReport:
        if home == bad:
            raise RuntimeError("episode buffer is corrupt")
        calls.append(home)
        return _report()

    scheduler = _scheduler(tmp_path, [bad, good], clock, calls, run_dream_fn=flaky)

    reports = await scheduler.sweep_once()

    assert calls == [good], "a raising home yields None and the sweep still visits the next one"
    assert reports == (None, _report())
    after = _home_lock(tmp_path / "locks", bad)
    assert after.acquire() is True, "a raising pass must not strand its lock"
    after.release()


async def test_the_evidence_write_happens_inside_the_lock_on_a_worker_thread(
    tmp_path: Path, clock: list[int]
) -> None:
    home = tmp_path / "a"
    lock_dir = tmp_path / "locks"
    loop_thread = threading.get_ident()
    observed: list[tuple[bool, bool]] = []

    def probing_writer(seen: Path, report: DreamReport | None, now_ms: int) -> None:
        del report, now_ms
        observed.append(
            (_home_lock(lock_dir, seen).is_locked(), threading.get_ident() != loop_thread)
        )

    def fake(
        seen: Path, *, now_ms: int, backfill: _Backfill | None, render: _Render | None
    ) -> DreamReport:
        del seen, now_ms, backfill, render
        return _report()

    scheduler = DreamScheduler(
        homes=lambda: [home],
        lock_dir=lock_dir,
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=fake,
        evidence_writer=probing_writer,
    )

    await scheduler.sweep_once()

    assert observed == [(True, True)], (
        "the write sits inside the mutual exclusion and off the event loop thread"
    )


async def test_two_homes_sharing_a_basename_get_distinct_locks(
    tmp_path: Path, clock: list[int]
) -> None:
    first = tmp_path / "one" / "asst"
    second = tmp_path / "two" / "asst"
    calls: list[Path] = []
    holder = _home_lock(tmp_path / "locks", first)
    assert holder.acquire() is True
    scheduler = _scheduler(tmp_path, [first, second], clock, calls)

    reports = await scheduler.sweep_once()

    assert calls == [second], "the lock key is the home path, so a basename twin is not skipped"
    assert reports == (None, _report())
    holder.release()


async def test_run_forever_survives_a_raising_homes_callable(
    tmp_path: Path, clock: list[int]
) -> None:
    ticks = 0
    scheduler: DreamScheduler | None = None

    def homes() -> list[Path]:
        nonlocal ticks
        ticks += 1
        if ticks == 1:
            raise OSError("assistant catalog listing failed")
        if scheduler is not None:
            scheduler.stop()
        return []

    scheduler = DreamScheduler(
        homes=homes,
        lock_dir=tmp_path / "locks",
        tick_seconds=0,
        now_ms=lambda: clock[0],
    )

    await asyncio.wait_for(scheduler.run_forever(), timeout=5)

    assert ticks == 2, "a raising homes callable is contained, the loop keeps ticking"
