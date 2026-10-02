"""CronJob contract tests (ADR-0268 §5, §6, §10).

验证模型层面的结构保证：一份定义一种 schedule、侧聊约束、
`space_action` 不带投递目标、投影字段闭集、类型化拒绝。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    CronListItem,
    CronRun,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    OneShotSchedule,
    ScheduledHandoff,
    SpaceActionExecution,
    TargetReceipt,
    WeeklySchedule,
)

NY = "America/New_York"


def _oneshot_job(**overrides: Any) -> CronJob:
    base: dict[str, Any] = {
        "id": "job_1",
        "title": "提醒",
        "schedule": OneShotSchedule(at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC)),
        "timezone": NY,
        "body": "提醒我开会",
        "execution": AgentExecution(),
        "delivery_targets": (ChatDelivery(chat_id="chat_1"),),
        "owner": "user_1",
        "created_chat_id": "chat_1",
        "anchor_at": datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return CronJob(**base)


def test_cron_job_accepts_each_schedule_kind() -> None:
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    schedules = (
        OneShotSchedule(at=now + timedelta(hours=1)),
        IntervalSchedule(every_seconds=60),
        HourlySchedule(minute=5),
        DailySchedule(hour=9, minute=0),
        WeeklySchedule(weekday=0, hour=9, minute=0),
    )
    for schedule in schedules:
        job = CronJob(
            id="job_x",
            title="t",
            schedule=schedule,
            timezone="UTC",
            body="b",
            execution=AgentExecution(),
            delivery_targets=(ChatDelivery(chat_id="chat_1"),),
            owner="o",
            created_chat_id="chat_1",
            anchor_at=now,
        )
        assert job.schedule.kind == schedule.kind


def test_cron_job_rejects_dual_schedule_fields() -> None:
    # IntervalSchedule 带 hourly 的字段 = 双 schedule 形状，extra="forbid" 拒绝。
    with pytest.raises(ValidationError):
        IntervalSchedule(every_seconds=60, minute=5)  # type: ignore[call-arg]


def test_cron_job_rejects_agent_without_delivery_target() -> None:
    with pytest.raises(ValidationError):
        _oneshot_job(delivery_targets=())


def test_cron_job_rejects_space_action_with_delivery_target() -> None:
    with pytest.raises(ValidationError):
        _oneshot_job(
            execution=SpaceActionExecution(artifact_id="art_1"),
            delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        )


def test_cron_job_rejects_cross_chat_delivery() -> None:
    # 侧聊任务不能投到主聊天。delivery_targets.chat_id 必须等于 created_chat_id。
    with pytest.raises(ValidationError):
        _oneshot_job(delivery_targets=(ChatDelivery(chat_id="other_chat"),))


def test_cron_job_rejects_naive_anchor_at() -> None:
    with pytest.raises(ValidationError):
        _oneshot_job(anchor_at=datetime(2026, 10, 2, 9, 0))  # naive


def test_cron_job_rejects_naive_oneshot_at() -> None:
    with pytest.raises(ValidationError):
        _oneshot_job(schedule=OneShotSchedule(at=datetime(2026, 10, 3, 9, 0)))  # naive


def test_cron_job_rejects_oneshot_at_in_dst_gap() -> None:
    # 2026-03-08 02:30 America/New_York 在春令时缺口里不存在。
    gap_at = datetime(2026, 3, 8, 2, 30, tzinfo=ZoneInfo(NY))
    with pytest.raises(ValidationError):
        _oneshot_job(
            schedule=OneShotSchedule(at=gap_at),
            timezone=NY,
        )


def test_cron_job_rejects_invalid_timezone() -> None:
    with pytest.raises(ValidationError):
        _oneshot_job(timezone="Not/AZone")


def test_cron_job_is_frozen() -> None:
    job = _oneshot_job()
    with pytest.raises(ValidationError):
        job.title = "其他标题"


def test_next_fire_contract_fields() -> None:
    from lca.contracts.models.cron.models import NextFire

    fire = NextFire(upcoming=datetime(2026, 10, 3, 9, 0, tzinfo=UTC), due=False)
    assert fire.upcoming == datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
    assert fire.due is False


def test_scheduled_handoff_rejects_missing_field() -> None:
    with pytest.raises(ValidationError):
        ScheduledHandoff(  # type: ignore[call-arg]
            job_id="job_1",
            run_id="run_1",
            task_context=_oneshot_job(),
            delivery_targets=(ChatDelivery(chat_id="chat_1"),),
            outcome="completed",
        )  # 缺 worker_message


def test_cron_run_contract() -> None:
    run = CronRun(
        run_id="run_1",
        outcome="completed",
        receipts=(TargetReceipt(chat_id=None, state="silent"),),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )
    assert run.outcome == "completed"
    assert run.receipts[0].state == "silent"


def test_cron_list_item_contract_fields() -> None:
    item = CronListItem(
        id="job_1",
        title="提醒",
        schedule_label="每天 09:00",
        next_run_local="2026-10-03 09:00",
        due=False,
        enabled=True,
        last_run_local="2026-10-02 09:01",
        last_delivery="silent",
    )
    assert item.next_run_local == "2026-10-03 09:00"
    assert item.last_delivery == "silent"


def test_cron_list_item_rejects_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        CronListItem(  # type: ignore[call-arg]
            id="job_1",
            schedule_label="每天 09:00",
            due=False,
            enabled=True,
        )  # 缺 title


def test_cron_list_item_rejects_schedule_field() -> None:
    with pytest.raises(ValidationError):
        CronListItem(
            id="job_1",
            title="t",
            schedule_label="每天 09:00",
            due=False,
            enabled=True,
            schedule=DailySchedule(hour=9, minute=0),  # type: ignore[call-arg]
        )


def test_cron_list_item_rejects_timezone_field() -> None:
    with pytest.raises(ValidationError):
        CronListItem(
            id="job_1",
            title="t",
            schedule_label="每天 09:00",
            due=False,
            enabled=True,
            timezone=NY,  # type: ignore[call-arg]
        )


def test_cron_list_item_rejects_anchor_at_field() -> None:
    with pytest.raises(ValidationError):
        CronListItem(
            id="job_1",
            title="t",
            schedule_label="每天 09:00",
            due=False,
            enabled=True,
            anchor_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),  # type: ignore[call-arg]
        )


def test_cron_list_item_rejects_every_seconds_field() -> None:
    with pytest.raises(ValidationError):
        CronListItem(
            id="job_1",
            title="t",
            schedule_label="每 60 秒",
            due=False,
            enabled=True,
            every_seconds=60,  # type: ignore[call-arg]
        )


def test_cron_list_item_rejects_at_field() -> None:
    with pytest.raises(ValidationError):
        CronListItem(
            id="job_1",
            title="t",
            schedule_label="一次性",
            due=False,
            enabled=True,
            at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC),  # type: ignore[call-arg]
        )
