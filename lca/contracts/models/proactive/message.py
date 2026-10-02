"""主动消息领域契约：消息、投递目标、触发源。

三层架构中的契约层（contracts）：只定义形状，不含行为。
触发层（infrastructure/proactive/scheduler）与投递层
（infrastructure/proactive/deliverer）都依赖本包，
裁决层（cognition/proactive/worthiness）消费本包。

设计约束（muse 思想）：
- 复用现有 surface 事件 taxonomy（``surface/assistant_message``），
  不新开消息协议；
- DeliveryTarget 显式声明投递落点，默认回发起上下文
 （对齐 side-chat 隔离：产出回原上下文）。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProactiveSource(StrEnum):
    """主动消息触发源。"""

    ONBOARDING_COMPLETED = "onboarding_completed"
    ROUTINE_CRON = "routine_cron"
    HOOK_EVENT = "hook_event"
    MANUAL = "manual"


class DeliveryTargetKind(StrEnum):
    """投递落点种类。"""

    SESSION_APPEND = "session_append"
    RESPONSE_CARRIED = "response_carried"


class DeliveryTarget(BaseModel):
    """主动消息投到哪里。

    - SESSION_APPEND：append 进指定 session 的 ``surface/assistant_message``
      事件（与前端读的是同一份 session log）；
    - RESPONSE_CARRIED：由触发请求的 HTTP 响应携带（如 onboarding
      naming_settle），不经过 session。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DeliveryTargetKind = Field(..., description="投递落点种类")
    session_id: str | None = Field(
        default=None,
        description="SESSION_APPEND 时的目标 session id",
    )

    @model_validator(mode="after")
    def validate_target(self) -> DeliveryTarget:
        if self.kind == DeliveryTargetKind.SESSION_APPEND and (
            not self.session_id or not self.session_id.strip()
        ):
            raise ValueError("SESSION_APPEND 必须指定非空 session_id")
        return self


class ProactiveMessage(BaseModel):
    """一条待投递的主动消息。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="消息唯一标识（幂等键）")
    content: str = Field(..., description="消息正文（assistant 气泡内容）")
    role: Literal["assistant"] = Field(default="assistant", description="固定 assistant")
    source: ProactiveSource = Field(..., description="触发源")
    requires_memory: bool = Field(
        default=False,
        description="内容是否依赖持久记忆；为 True 且无记忆源时裁决层降级",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="透传元数据（如 onboarding 的 assistant_name）",
    )

    @model_validator(mode="after")
    def validate_message(self) -> ProactiveMessage:
        if not self.id.strip():
            raise ValueError("id 不能为空")
        if not self.content.strip():
            raise ValueError("content 不能为空")
        return self


__all__ = [
    "DeliveryTarget",
    "DeliveryTargetKind",
    "ProactiveMessage",
    "ProactiveSource",
]
