"""CronJob contract models (ADR-0268 §5, §6, §10).

一份定义，一种 schedule。`CronJob` 是「即将到来」投影的唯一数据源；
run 记录只追加在 ``cron/<job_id>/runs/``，不在这里。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AgentExecution",
    "ChatDelivery",
    "CronJob",
    "CronListItem",
    "CronRun",
    "CronValidationError",
    "DailySchedule",
    "HourlySchedule",
    "IntervalSchedule",
    "NextFire",
    "OneShotSchedule",
    "ScheduledHandoff",
    "SpaceActionExecution",
    "TargetReceipt",
    "WeeklySchedule",
]


class CronValidationError(ValueError):
    """Type-level rejection for cron inputs (ADR-0268 §13).

    调用方捕获它得到类型化拒绝；不抛裸异常。
    """


class OneShotSchedule(BaseModel):
    """一次性提醒。只在这一刻触发一次，不展开成周期。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["oneshot"] = "oneshot"
    at: datetime  # aware。调用方构造的 at 若落在时区缺口，模型校验时拒绝


class IntervalSchedule(BaseModel):
    """固定间隔。相位从 CronJob.anchor_at 起算。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["interval"] = "interval"
    every_seconds: int = Field(..., gt=0)


class HourlySchedule(BaseModel):
    """每小时触发。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["hourly"] = "hourly"
    minute: int = Field(..., ge=0, le=59)


class DailySchedule(BaseModel):
    """每天触发。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["daily"] = "daily"
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)


class WeeklySchedule(BaseModel):
    """每周触发。weekday 0 = 周一 … 6 = 周日。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["weekly"] = "weekly"
    weekday: int = Field(..., ge=0, le=6)
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)


class AgentExecution(BaseModel):
    """cron worker 作为独立 turn loop 的 agent 执行。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["agent"] = "agent"


class SpaceActionExecution(BaseModel):
    """cron worker 只更新指定 artifact，不产生 handoff。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["space_action"] = "space_action"
    artifact_id: str = Field(..., min_length=1)


class ChatDelivery(BaseModel):
    """一个投递目标 chat。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chat_id: str = Field(..., min_length=1)


def _wall_clock_exists(local: datetime) -> bool:
    """该墙钟是否真实存在（不在 DST 缺口）。

    ``ZoneInfo`` 对缺口时间返回 gap 前的偏移，``utcoffset() is None``
    检测不到；正确做法是转 UTC 再转回，看墙钟是否一致。
    """
    if local.utcoffset() is None:
        return False
    back = local.astimezone(UTC).astimezone(local.tzinfo)
    return back == local


class CronJob(BaseModel):
    """一份 cron 任务定义（ADR-0268 §5）。

    - ``schedule`` 是 discriminated union，同一时刻只有一种 schedule。
    - ``timezone`` 缺省由服务端填用户的 client_timezone；取不到或
      ``ZoneInfo`` 无法加载则拒绝本次 ``cron.add``。
    - ``anchor_at`` 由服务端在 ``cron.add`` 时写入，调用方不能传。
    - 模型校验时即检查 aware、时区可加载、``at`` 不在 DST 缺口。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    schedule: (
        OneShotSchedule | IntervalSchedule | HourlySchedule | DailySchedule | WeeklySchedule
    ) = Field(discriminator="kind")
    timezone: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    execution: AgentExecution | SpaceActionExecution = Field(discriminator="kind")
    delivery_targets: tuple[ChatDelivery, ...] = ()
    report: Literal["always", "anomalies_only"] = "anomalies_only"
    owner: str = Field(..., min_length=1)
    created_chat_id: str = Field(..., min_length=1)
    anchor_at: datetime  # aware。服务端写入，调用方不能传
    enabled: bool = True
    max_retries: int = Field(default=0, ge=0)
    timeout_seconds: int | None = None

    @model_validator(mode="after")
    def validate_cron_job(self) -> CronJob:
        if self.execution.kind == "agent" and not self.delivery_targets:
            raise ValueError("agent execution requires at least one delivery_target")
        if self.execution.kind == "space_action" and self.delivery_targets:
            raise ValueError("space_action execution must not carry delivery_targets")
        for target in self.delivery_targets:
            if target.chat_id != self.created_chat_id:
                raise ValueError("delivery_targets must match created_chat_id")
        if self.anchor_at.tzinfo is None or self.anchor_at.utcoffset() is None:
            raise ValueError("anchor_at must be timezone-aware")
        try:
            tz = ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError(f"invalid timezone {self.timezone!r}") from exc
        if self.schedule.kind == "oneshot":
            at = self.schedule.at
            if at.tzinfo is None or at.utcoffset() is None:
                raise ValueError("oneshot at must be timezone-aware")
            local = at.astimezone(tz)
            if not _wall_clock_exists(local):
                raise ValueError("oneshot at falls in a DST gap")
        return self


class NextFire(BaseModel):
    """``next_run`` 的纯函数结果（ADR-0268 §5）。

    ``upcoming`` 有值则严格晚于 ``now``，且是该 timezone 的 aware datetime。
    ``due`` 表示这一刻要触发；它不是时间戳。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    upcoming: datetime | None
    due: bool


class TargetReceipt(BaseModel):
    """一次投递目标的回执（ADR-0268 §6）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chat_id: str | None
    state: Literal["delivered", "failed", "silent", "not_sent"]


class CronRun(BaseModel):
    """一条 cron run 记录（只追加，ADR-0268 §6）。

    ``receipts`` 在投递决定写下之前可以为空（未决）；``finished_at``
    记下 worker 结束时间。``superseded`` 和成功的 ``space_action``
    追加时就写上 ``not_sent``。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(..., min_length=1)
    outcome: Literal["completed", "runtime_failure", "timed_out", "superseded"]
    receipts: tuple[TargetReceipt, ...] = ()
    finished_at: datetime | None = None


class ScheduledHandoff(BaseModel):
    """注入父对话的 cron handoff（ADR-0268 §6）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    task_context: CronJob
    worker_message: str
    delivery_targets: tuple[ChatDelivery, ...]
    outcome: Literal["completed", "runtime_failure", "timed_out"]


class CronListItem(BaseModel):
    """「即将到来」列表投影字段闭集（ADR-0268 §10）。

    契约明确禁止把 ``schedule``、``timezone``、``anchor_at``、
    ``every_seconds``、``at`` 暴露给列表。客户端只用 ``next_run_local``
    字符串展示时间，不在浏览器里推算。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    schedule_label: str = Field(..., min_length=1)
    next_run_local: str | None = None
    due: bool
    enabled: bool
    last_run_local: str | None = None
    last_delivery: Literal["delivered", "failed", "silent", "not_sent"] | None = None
