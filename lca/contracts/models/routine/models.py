"""Routine domain contract models (ADR-0248 §3.4, §5.1 / s04, s14)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoutineSpec(BaseModel):
    """声明式后台自驱例程定义。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="例程唯一标识符（如 rt_check_build）")
    name: str = Field(..., description="例程业务展示名称")
    prompt: str = Field(..., description="意图型执行提示词")
    spend_budget_per_run: int = Field(default=15, description="单次执行最大推理步数上限")
    daily_budget_tokens: int = Field(default=100_000, description="单日 Token 消耗硬熔断上限")
    enabled: bool = Field(default=True, description="是否启用当前例程")
    assistant_id: str = Field(..., description="所属绑定的 Assistant ID")
    interval_s: int | None = Field(
        default=None,
        description="触发间隔（秒）；ADR-0248 §3.4 承诺的 Cron/间隔周期判定一直缺这个字段，"
        "ADR-0263 §8 时间窗口判定与 §9 stale 默认（2x interval，上限 90min）需要它。"
        "None 表示未声明周期（手动/事件驱动型），调度窗口回退到生产约定（见 scheduler）。",
    )

    @model_validator(mode="after")
    def validate_routine_semantics(self) -> RoutineSpec:
        if not self.id.strip():
            raise ValueError("id 不能为空")
        if not self.name.strip():
            raise ValueError("name 不能为空")
        if not self.prompt.strip():
            raise ValueError("prompt 不能为空")
        if not self.assistant_id.strip():
            raise ValueError("assistant_id 不能为空")
        if self.spend_budget_per_run <= 0:
            raise ValueError("spend_budget_per_run 必须大于 0")
        if self.daily_budget_tokens <= 0:
            raise ValueError("daily_budget_tokens 必须大于 0")
        if self.interval_s is not None and self.interval_s <= 0:
            raise ValueError("interval_s 必须大于 0")
        return self


class RoutineTrigger(BaseModel):
    """例程触发事件记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    routine_id: str = Field(..., description="触发的例程 ID")
    triggered_at_ms: int = Field(..., description="触发时刻毫秒时间戳")
    trigger_source: str = Field(default="cron", description="触发源 (cron | interval | manual)")


class SpendBudget(BaseModel):
    """例程执行消费预算状态。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    daily_budget_tokens: int = Field(default=100_000, description="每日 Token 上限")
    max_steps_per_run: int = Field(default=15, description="单轮最大步数")
    tokens_consumed_today: int = Field(default=0, description="本日累计已消耗 Token")

    @property
    def remaining_tokens_today(self) -> int:
        return max(0, self.daily_budget_tokens - self.tokens_consumed_today)

    @property
    def is_exhausted(self) -> bool:
        return self.tokens_consumed_today >= self.daily_budget_tokens
