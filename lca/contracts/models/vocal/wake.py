from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class WakeSource(StrEnum):
    """唤醒源闭集分类（ADR-0248 §3.4）。"""

    USER_INPUT = "user_input"
    FIRST_RUN = "first_run"
    INBOUND = "inbound"
    ROUTINE = "routine"
    PEER_AGENT = "peer_agent"
    REVIVAL = "revival"


class WakeContext(BaseModel):
    """唤醒上下文与行为约束。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: WakeSource = Field(..., description="唤醒源")
    is_silence_allowed: bool = Field(
        default=False, description="是否允许无变化时完全沉默收敛"
    )
    requires_reply_first: bool = Field(
        default=False, description="是否要求首个动作为承接回复"
    )
    channel_target: str | None = Field(default=None, description="入站渠道标识")
    subagent_id: str | None = Field(
        default=None, description="复苏事件关联的子代理ID"
    )
    priority: bool = Field(default=False, description="是否为高优先级打断唤醒")
