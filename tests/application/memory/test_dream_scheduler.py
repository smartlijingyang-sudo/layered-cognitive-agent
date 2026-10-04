from pathlib import Path

import pytest

from lca.application.memory.dream_scheduler import DreamScheduler


@pytest.fixture
def clock() -> list[int]:
    return [1_791_121_000_000]


def _scheduler(tmp_path: Path, homes: list[Path], clock: list[int], calls: list[Path]):
    def fake_run_dream(home, *, now_ms, backfill, render):
        calls.append(home)
        return None

    return DreamScheduler(
        homes=lambda: homes,
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        run_dream_fn=fake_run_dream,
        evidence_writer=lambda home, report, now_ms: None,
    )


async def test_sweep_once_visits_every_home(tmp_path: Path, clock: list[int]) -> None:
    homes = [tmp_path / "a", tmp_path / "b"]
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, homes, clock, calls)

    await scheduler.sweep_once()

    assert calls == homes


async def test_interval_skips_a_sweep_that_is_not_due_yet(tmp_path: Path, clock: list[int]) -> None:
    calls: list[Path] = []
    scheduler = _scheduler(tmp_path, [tmp_path / "a"], clock, calls)

    await scheduler.sweep_once()
    await scheduler.sweep_once()

    assert calls == [tmp_path / "a"], "second sweep is inside the 300s interval"

    clock[0] += 300_000
    await scheduler.sweep_once()

    assert calls == [tmp_path / "a", tmp_path / "a"]
