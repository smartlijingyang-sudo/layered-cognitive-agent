"""主动消息调度契约（对齐 ADR-0263）。

- 锁：文件锁（锁目录 + mtime 心跳 + stale 收割），单机 carrier 形态；
- stale 阈值：默认 2×interval，可配，绝对上限 90 分钟；
- 重试：3 次，退避 1min / 5min / 15min，3 次后进死信；
- 死信：保留 7 天可查；
- tick 驱动落点：carrier 内（由 carrier 生命周期调用 ``tick``）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lca.contracts.models.proactive.message import DeliveryTarget, ProactiveSource


class ProactiveJob(BaseModel):
    """一条定时主动消息任务。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="任务唯一标识")
    interval_seconds: int = Field(..., description="触发间隔（秒）")
    content: str = Field(..., description="消息正文模板")
    source: ProactiveSource = Field(
        default=ProactiveSource.ROUTINE_CRON,
        description="触发源",
    )
    target: DeliveryTarget = Field(..., description="投递落点")
    requested: bool = Field(default=False, description="是否用户明确要求")
    request_ref: str | None = Field(
        default=None,
        description="requested=True 时的引用 ID；须为 job:<id> 形式，由 scheduler 以任务定义背书，gate 做机械校验",
    )
    worth_interrupting: bool = Field(default=False, description="是否值得打断")
    enabled: bool = Field(default=True, description="是否启用")
    stale_multiplier: float = Field(
        default=2.0,
        description="stale 阈值 = interval × 本系数（ADR-0263 §9②）",
    )

    @model_validator(mode="after")
    def validate_job(self) -> ProactiveJob:
        if not self.id.strip():
            raise ValueError("id 不能为空")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds 必须大于 0")
        if not self.content.strip():
            raise ValueError("content 不能为空")
        return self


class TickReport(BaseModel):
    """一次 tick 的执行报告。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tick_at_ms: int = Field(..., description="tick 时刻（毫秒）")
    lock_acquired: bool = Field(..., description="是否拿到文件锁")
    jobs_due: int = Field(default=0, description="到期任务数")
    delivered: int = Field(default=0, description="成功投递数")
    silent: int = Field(default=0, description="静默数")
    rejected: int = Field(default=0, description="拒绝数")
    failed: int = Field(default=0, description="失败数（含重试中）")
    dead_lettered: int = Field(default=0, description="本次进死信数")


__all__ = ["ProactiveJob", "TickReport"]
