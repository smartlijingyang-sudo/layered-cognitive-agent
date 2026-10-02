"""主动消息全局政策（ProactivePolicy）。

muse 思想注记：
- 粒度只到**全局总开关**，不做 per-source 四档（YAGNI：今天没有
  四个源需要不同政策的实证）；
- gate 是**唯一卡点**：scheduler/手动/onboarding 所有路径必经 gate，
  ``enabled=False`` → SILENT；per-job ``enabled`` 保留（job 级启停
  与全局开关正交：前者是"我这个任务暂停"，后者是"整个主动消息停"）；
- quiet hours 内裁决上限为 DELIVER_QUIET（消息照投递，只是不打断）；
  频次上限留扩展点，不实现（YAGNI）。
"""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, ConfigDict, Field


class ProactivePolicy(BaseModel):
    """主动消息全局政策。frozen：运行时配置，裁决中只读。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = Field(
        default=True,
        description="全局总开关；False 时 gate 一律 SILENT（REJECTED 除外）",
    )
    quiet_hours_start: time = Field(
        default=time(22, 0),
        description="quiet hours 起（含）；与 end 相同视为未设置",
    )
    quiet_hours_end: time = Field(
        default=time(8, 0),
        description="quiet hours 止（不含）",
    )
    timezone: str = Field(
        default="Asia/Shanghai",
        description="quiet hours 所在时区（IANA 名）；配错时 gate 记 warning 并跳过限流，不炸 tick",
    )


__all__ = ["ProactivePolicy"]
