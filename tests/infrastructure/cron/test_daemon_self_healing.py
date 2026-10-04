"""CronDaemonService lifecycle and CronWorkerRunner reporting (ADR-0268 §3.4, §6).

The worker reports; it does not deliver. Every test here pins that split, so a
regression that puts a chat write back into the worker fails on an assertion
about receipts or about a session store the runner no longer accepts.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    OneShotSchedule,
    SpaceActionExecution,
)
from lca.domain.cron.store import CronStore
from lca.domain.cron.worker_context import (
    CronWorkerResult,
    WorkerProductContext,
    assemble_worker_context,
)
from lca.infrastructure.cron.daemon import CronDaemonService
from lca.infrastructure.cron.worker_runner import CronWorkerRunner


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        store = CronStore(p / "assistant_home")
        lock_dir = p / "locks"
        yield store, lock_dir, p


def _product_context(job: CronJob) -> WorkerProductContext:
    return WorkerProductContext(
        job_id=job.id,
        owner=job.owner,
        workspace_path="assistant-workspace",
        timezone=job.timezone,
        report=job.report,
        delivery_targets=job.delivery_targets,
        run_id=f"{job.id}-run1",
    )


def _job(
    store: CronStore,
    *,
    job_id: str = "job-1",
    body: str = "李超，记得喝水！",
    execution: AgentExecution | SpaceActionExecution | None = None,
    targets: tuple[ChatDelivery, ...] = (ChatDelivery(chat_id="tpc_target"),),
) -> CronJob:
    job = CronJob(
        id=job_id,
        title="喝水提醒",
        body=body,
        schedule=OneShotSchedule(
            at=datetime(2026, 10, 3, 21, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
        ),
        timezone="Asia/Shanghai",
        execution=execution or AgentExecution(),
        owner="asst_123",
        created_chat_id="tpc_target",
        delivery_targets=targets,
        anchor_at=datetime(2026, 10, 3, 13, 0, tzinfo=UTC),
    )
    store.save_job(job)
    return job


@pytest.mark.asyncio
async def test_agent_job_reports_its_body_and_owes_a_receipt(temp_env):
    """An agent handoff leaves receipts empty, which ADR-0268 §6 reads as pending.

    The handoff turn closes them. Empty here is not the old orphan-session
    defect, where the worker claimed a delivery it had fabricated; nothing in
    this result asserts a chat write happened.
    """
    store, _lock_dir, _tmp = temp_env
    job = _job(store)

    result: CronWorkerResult = await CronWorkerRunner(store=store)(job)

    assert result.outcome == "completed"
    assert result.worker_message == "李超，记得喝水！"
    assert result.receipts == ()


@pytest.mark.asyncio
async def test_space_action_writes_not_sent_because_it_has_no_parent_turn(temp_env):
    store, _lock_dir, _tmp = temp_env
    job = _job(
        store,
        execution=SpaceActionExecution(artifact_id="artifact-1"),
        targets=(),
    )

    result = await CronWorkerRunner(store=store)(job)

    assert result.outcome == "completed"
    assert result.worker_message == ""
    assert [(r.chat_id, r.state) for r in result.receipts] == [(None, "not_sent")]


@pytest.mark.asyncio
async def test_context_text_round_trips_back_to_the_stored_job(temp_env):
    store, _lock_dir, _tmp = temp_env
    job = _job(store, job_id="job-roundtrip")
    text = assemble_worker_context(job.body, _product_context(job))

    result = await CronWorkerRunner(store=store)(text)

    assert result.worker_message == job.body


@pytest.mark.asyncio
async def test_text_without_a_job_id_reports_runtime_failure(temp_env):
    store, _lock_dir, _tmp = temp_env

    result = await CronWorkerRunner(store=store)("no job id in here")

    assert result.outcome == "runtime_failure"
    assert [(r.chat_id, r.state) for r in result.receipts] == [(None, "not_sent")]


@pytest.mark.asyncio
async def test_unknown_job_id_reports_runtime_failure(temp_env):
    store, _lock_dir, _tmp = temp_env

    result = await CronWorkerRunner(store=store)("- job_id: job_never_saved\n")

    assert result.outcome == "runtime_failure"
    assert result.worker_message == ""


@pytest.mark.asyncio
async def test_daemon_lifecycle_start_stop(temp_env):
    store, lock_dir, tmp = temp_env
    now_clock = datetime(2026, 10, 3, 22, 0, tzinfo=UTC)
    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp),
        tick_interval_s=1,
        clock=lambda: now_clock,
    )

    await daemon.start()
    assert daemon.is_running is True

    await daemon.stop()
    assert daemon.is_running is False


@pytest.mark.asyncio
async def test_daemon_tick_appends_a_pending_run_record(temp_env):
    store, lock_dir, tmp = temp_env
    job = _job(
        store,
        job_id="job-tick-due-1",
        body="这是测试消息",
    )
    now_clock = datetime(2026, 10, 3, 21, 25, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp),
        tick_interval_s=1,
        clock=lambda: now_clock,
    )

    report = await daemon.tick(now_clock)
    assert report.due == 1
    assert report.started == 1

    await daemon._scheduler.wait_idle()

    runs = store.list_runs(job.id)
    assert len(runs) == 1
    assert runs[0].outcome == "completed"
    assert runs[0].receipts == ()
