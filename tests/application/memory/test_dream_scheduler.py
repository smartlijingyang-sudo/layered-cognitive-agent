import asyncio
from pathlib import Path

import pytest

from lca.application.memory.dream_scheduler import DreamScheduler, _Backfill, _Render
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
        run_dream_fn=fake_run_dream,
        evidence_writer=write_evidence,
    )


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
    assert await scheduler.sweep_once() == (), "second sweep is inside the 300s interval"

    assert calls == [tmp_path / "a"], "second sweep is inside the 300s interval"

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
