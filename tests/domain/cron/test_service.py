"""CronService tests (ADR-0268 §5, §6, §10).

验证：「即将到来」投影字段闭集、``next_run_local`` 与墙钟一致、
停用任务 due 强制为假、已完成 oneshot 不进入列表、重复 id 不覆盖、
``last_delivery`` 汇总规则。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    CronRun,
    DailySchedule,
    OneShotSchedule,
    TargetReceipt,
)
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore


def _service(tmp_path: Path) -> CronService:
    return CronService(CronStore(tmp_path))


def _job(**overrides: Any) -> CronJob:
    base: dict[str, Any] = {
        "id": "job_1",
        "title": "每日提醒",
        "schedule": DailySchedule(hour=9, minute=0),
        "timezone": "Asia/Shanghai",
        "body": "提醒我同步进度",
        "execution": AgentExecution(),
        "delivery_targets": (ChatDelivery(chat_id="chat_1"),),
        "report": "anomalies_only",
        "owner": "user_1",
        "created_chat_id": "chat_1",
        "anchor_at": datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return CronJob(**base)


def test_add_job_and_duplicate_id_returns_existing(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    job = svc.add_job(
        id="job_1",
        title="每日提醒",
        schedule=DailySchedule(hour=9, minute=0),
        timezone="Asia/Shanghai",
        body="b",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        report="anomalies_only",
        owner="user_1",
        created_chat_id="chat_1",
        now=now,
    )
    assert job.anchor_at == now
    again = svc.add_job(
        id="job_1",
        title="另一个标题",
        schedule=DailySchedule(hour=8, minute=0),
        timezone="Asia/Shanghai",
        body="b2",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        report="always",
        owner="user_1",
        created_chat_id="chat_1",
        now=now,
    )
    assert again.title == "每日提醒"


def test_list_items_projection(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    svc.add_job(
        id="job_1",
        title="每日提醒",
        schedule=DailySchedule(hour=9, minute=0),
        timezone="Asia/Shanghai",
        body="b",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        report="anomalies_only",
        owner="user_1",
        created_chat_id="chat_1",
        now=now,
    )
    items = svc.list_items(owner="user_1", now=now)
    assert len(items) == 1
    item = items[0]
    assert item.id == "job_1"
    assert item.schedule_label == "每天 09:00"
    # now 是 09:00 整（Asia/Shanghai 与 UTC 同一天内差 8 小时，UTC 09:00 = 上海 17:00）
    assert item.next_run_local == "2026-10-03 09:00"
    assert item.due is False
    assert item.enabled is True
    assert item.last_run_local is None
    assert item.last_delivery is None


def test_list_items_disabled_forces_due_false(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    job = _job(id="job_1", enabled=False)
    svc._store.save_job(job)
    items = svc.list_items(owner="user_1", now=now)
    assert items[0].enabled is False
    assert items[0].due is False
    # 停用任务仍带 next_run_local。
    assert items[0].next_run_local is not None


def test_list_items_hides_completed_oneshot(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    job = _job(
        id="job_1",
        schedule=OneShotSchedule(at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
    )
    svc._store.save_job(job)
    # 追加一条已完成 run：oneshot 已完成 → 不进入即将到来。
    run = CronRun(
        run_id="run_1",
        outcome="completed",
        receipts=(TargetReceipt(chat_id=None, state="silent"),),
        finished_at=datetime(2026, 10, 1, 9, 1, tzinfo=UTC),
    )
    svc._store.append_run(
        "job_1",
        run_id=run.run_id,
        outcome=run.outcome,
        receipts=run.receipts,
        finished_at=run.finished_at,
    )
    items = svc.list_items(owner="user_1", now=now)
    assert items == []


def test_list_items_keeps_a_fired_oneshot_whose_receipts_are_still_pending(
    tmp_path: Path,
) -> None:
    """Empty receipts mean the handoff turn still owes a decision (ADR-0268 §6).

    Hiding the job here would make an undelivered fire invisible: the run record
    is the only carrier of ``last_delivery``, so filtering on it and reading the
    badge from it cannot both happen.
    """
    svc = _service(tmp_path)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    job = _job(
        id="job_pending",
        schedule=OneShotSchedule(at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
    )
    svc._store.save_job(job)
    svc._store.append_run(
        "job_pending",
        run_id="run_pending",
        outcome="completed",
        receipts=(),
        finished_at=datetime(2026, 10, 1, 9, 1, tzinfo=UTC),
    )

    items = svc.list_items(owner="user_1", now=now)

    assert [item.id for item in items] == ["job_pending"]
    assert items[0].last_delivery is None
    assert items[0].last_run_local is not None


def test_last_delivery_summary_prefers_failed(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    job = _job(id="job_1")
    svc._store.save_job(job)
    run = CronRun(
        run_id="run_1",
        outcome="completed",
        receipts=(
            TargetReceipt(chat_id="chat_1", state="delivered"),
            TargetReceipt(chat_id="chat_2", state="failed"),
        ),
        finished_at=datetime(2026, 10, 1, 9, 1, tzinfo=UTC),
    )
    svc._store.append_run(
        "job_1",
        run_id=run.run_id,
        outcome=run.outcome,
        receipts=run.receipts,
        finished_at=run.finished_at,
    )
    items = svc.list_items(owner="user_1", now=datetime(2026, 10, 2, 9, 0, tzinfo=UTC))
    assert items[0].last_delivery == "failed"


def test_replace_and_remove(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    job = _job(id="job_1")
    svc._store.save_job(job)
    svc.replace_job(job.model_copy(update={"title": "新标题"}))
    assert svc.get_job("job_1") is not None
    assert svc.get_job("job_1").title == "新标题"  # type: ignore[union-attr]
    assert svc.remove_job("job_1") is True
    assert svc.get_job("job_1") is None
