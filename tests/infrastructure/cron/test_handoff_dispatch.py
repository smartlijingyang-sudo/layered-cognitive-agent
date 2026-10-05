"""ADR-0268 §6.1: the scheduler hands off, and the handoff turn closes receipts.

Uses a fake dispatcher so the assertions are about ordering and about what lands
on the run record, not about starting real runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    OneShotSchedule,
    ScheduledHandoff,
    SpaceActionExecution,
)
from lca.domain.cron.handoff_dispatch import render_handoff_text
from lca.domain.cron.store import CronStore
from lca.infrastructure.cron.scheduler import CronScheduler

_NOW = datetime(2026, 10, 5, 9, 5, tzinfo=UTC)


class _FakeDispatcher:
    def __init__(self, state: str = "delivered", *, raises: bool = False) -> None:
        self.state = state
        self.raises = raises
        self.dispatched: list[tuple[str, str]] = []
        self.awaited: list[str] = []

    async def dispatch(self, handoff: ScheduledHandoff, *, target: ChatDelivery) -> str:
        if self.raises:
            raise RuntimeError("no run port")
        run_id = f"run_handoff_{len(self.dispatched)}"
        self.dispatched.append((handoff.job_id, target.chat_id))
        return run_id

    async def await_receipt(self, run_id: str) -> str:
        self.awaited.append(run_id)
        return self.state


def _store(tmp_path: Path) -> CronStore:
    return CronStore(tmp_path / "home")


def _job(
    store: CronStore,
    *,
    job_id: str = "job_h",
    execution: AgentExecution | SpaceActionExecution | None = None,
    targets: tuple[ChatDelivery, ...] = (ChatDelivery(chat_id="tpc_1"),),
) -> CronJob:
    job = CronJob(
        id=job_id,
        title="散步提醒",
        body="该出去走走了",
        schedule=OneShotSchedule(at=datetime(2026, 10, 5, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))),
        timezone="Asia/Shanghai",
        execution=execution or AgentExecution(),
        owner="asst_1",
        created_chat_id="tpc_1",
        delivery_targets=targets,
        anchor_at=datetime(2026, 10, 5, 8, 0, tzinfo=UTC),
    )
    store.save_job(job)
    return job


def _scheduler(store: CronStore, tmp_path: Path, dispatcher: object | None) -> CronScheduler:
    async def _worker(_text: str):
        from lca.domain.cron.worker_context import CronWorkerResult

        return CronWorkerResult(outcome="completed", worker_message="该出去走走了")

    return CronScheduler(
        store=store,
        lock_dir=tmp_path / "locks",
        workspace_path=str(tmp_path),
        worker_runner=_worker,
        clock=lambda: _NOW,
        handoff_dispatcher=dispatcher,
    )


async def _settle(scheduler: CronScheduler) -> None:
    await scheduler.wait_idle()
    while scheduler._handoff_tasks:
        await scheduler.wait_idle()
        for task in tuple(scheduler._handoff_tasks):
            await task


def test_render_handoff_text_carries_the_occurrence_and_the_rule() -> None:
    job = CronJob(
        id="job_h",
        title="散步提醒",
        body="该出去走走了",
        schedule=OneShotSchedule(at=_NOW),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="asst_1",
        created_chat_id="tpc_1",
        delivery_targets=(ChatDelivery(chat_id="tpc_1"),),
        anchor_at=_NOW,
    )
    handoff = ScheduledHandoff(
        job_id="job_h",
        run_id="job_h-occ1",
        task_context=job,
        worker_message="该出去走走了",
        delivery_targets=job.delivery_targets,
        outcome="completed",
    )

    text = render_handoff_text(handoff)

    assert "job_h" in text
    assert "job_h-occ1" in text
    assert "该出去走走了" in text
    assert "anomalies_only" in text
    assert "lca.nothing_to_do" in text


@pytest.mark.asyncio
async def test_a_fired_agent_job_dispatches_and_closes_its_receipt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _job(store)
    dispatcher = _FakeDispatcher("delivered")
    scheduler = _scheduler(store, tmp_path, dispatcher)

    await scheduler.tick(_NOW)
    await _settle(scheduler)

    assert dispatcher.dispatched == [("job_h", "tpc_1")]
    assert dispatcher.awaited == ["run_handoff_0"]
    runs = store.list_runs("job_h")
    assert len(runs) == 1
    assert runs[0].handoff_run_ids == ("run_handoff_0",)
    assert [(r.chat_id, r.state) for r in runs[0].receipts] == [("tpc_1", "delivered")]


@pytest.mark.asyncio
async def test_a_silent_handoff_turn_records_silent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _job(store)
    scheduler = _scheduler(store, tmp_path, _FakeDispatcher("silent"))

    await scheduler.tick(_NOW)
    await _settle(scheduler)

    receipts = store.list_runs("job_h")[0].receipts
    assert [(r.chat_id, r.state) for r in receipts] == [("tpc_1", "silent")]


@pytest.mark.asyncio
async def test_a_dispatch_that_raises_records_failed_and_leaves_no_identity(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _job(store)
    scheduler = _scheduler(store, tmp_path, _FakeDispatcher(raises=True))

    await scheduler.tick(_NOW)
    await _settle(scheduler)

    run = store.list_runs("job_h")[0]
    assert run.handoff_run_ids == ()
    assert [(r.chat_id, r.state) for r in run.receipts] == [("tpc_1", "failed")]


@pytest.mark.asyncio
async def test_without_a_dispatcher_the_record_stays_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _job(store)
    scheduler = _scheduler(store, tmp_path, None)

    await scheduler.tick(_NOW)
    await _settle(scheduler)

    run = store.list_runs("job_h")[0]
    assert run.outcome == "completed"
    assert run.receipts == ()
    assert run.handoff_run_ids == ()


@pytest.mark.asyncio
async def test_a_job_with_no_delivery_target_does_not_dispatch(tmp_path: Path) -> None:
    """CronJob rejects a space_action that carries targets, so this is the only
    shape with an execution kind and nothing to deliver to."""
    store = _store(tmp_path)
    _job(store, execution=SpaceActionExecution(artifact_id="a1"), targets=())
    dispatcher = _FakeDispatcher("delivered")
    scheduler = _scheduler(store, tmp_path, dispatcher)

    await scheduler.tick(_NOW)
    await _settle(scheduler)

    assert dispatcher.dispatched == []
    assert store.list_runs("job_h")[0].handoff_run_ids == ()
