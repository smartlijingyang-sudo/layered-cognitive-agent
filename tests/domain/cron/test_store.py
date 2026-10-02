"""CronStore file storage tests (ADR-0268 §5, §6).

验证：定义原子写与读回、列表、删除只删定义不删 run、run 记录追加。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    CronRun,
    DailySchedule,
    TargetReceipt,
)
from lca.domain.cron.store import CronStore

UTC = UTC


def _job(job_id: str = "job_1") -> CronJob:
    return CronJob(
        id=job_id,
        title="每日提醒",
        schedule=DailySchedule(hour=9, minute=0),
        timezone="Asia/Shanghai",
        body="提醒我同步进度",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        owner="user_1",
        created_chat_id="chat_1",
        anchor_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    )


def test_save_and_get_roundtrip(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.save_job(_job())
    loaded = store.get_job("job_1")
    assert loaded is not None
    assert loaded.id == "job_1"
    assert loaded.title == "每日提醒"
    assert loaded.schedule.kind == "daily"
    assert loaded.timezone == "Asia/Shanghai"


def test_get_missing_returns_none(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    assert store.get_job("nope") is None


def test_list_jobs(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.save_job(_job("job_1"))
    store.save_job(_job("job_2"))
    jobs = store.list_jobs()
    assert [j.id for j in jobs] == ["job_1", "job_2"]


def test_delete_job_keeps_runs(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.save_job(_job())
    run = CronRun(
        run_id="run_1",
        outcome="completed",
        receipts=(TargetReceipt(chat_id=None, state="silent"),),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )
    store.append_run(
        "job_1",
        run_id=run.run_id,
        outcome=run.outcome,
        receipts=run.receipts,
        finished_at=run.finished_at,
    )

    assert store.delete_job("job_1") is True
    assert store.get_job("job_1") is None
    # run 记录保留，仍可读。
    assert store.get_run("job_1", "run_1") == run
    assert store.list_runs("job_1") == [run]


def test_delete_missing_returns_false(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    assert store.delete_job("nope") is False


def test_append_and_list_runs(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.append_run("job_1", run_id="run_1", outcome="completed")
    store.append_run("job_1", run_id="run_2", outcome="timed_out")
    assert [r.run_id for r in store.list_runs("job_1")] == ["run_1", "run_2"]
    assert store.get_run("job_1", "run_2") == CronRun(run_id="run_2", outcome="timed_out")


def test_append_run_generates_run_id(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    rid = store.append_run(
        "job_1",
        outcome="completed",
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )
    assert rid.startswith("job_1-")
    run = store.get_run("job_1", rid)
    assert run is not None
    assert run.outcome == "completed"
    assert run.finished_at == datetime(2026, 10, 2, 9, 1, tzinfo=UTC)
    assert run.receipts == ()


def test_get_run_records(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.append_run("job_1", run_id="r1", outcome="completed")
    store.append_run("job_1", run_id="r2", outcome="runtime_failure")
    assert [r.run_id for r in store.get_run_records("job_1")] == ["r1", "r2"]
