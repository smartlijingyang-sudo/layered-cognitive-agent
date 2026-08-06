"""任务生命周期与跨 Agent 通信契约 —— TaskStatus / AgentCard / TeamMessage 唯一定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from lca.contracts.atoms.enums import DelegationProtocol
from lca.contracts.atoms.ids import utc_now


class TaskStatus(str, Enum):
    """Agent / Team 任务生命周期状态（A2A 兼容）。"""

    SUBMITTED = "submitted"
    WORKING = "working"
    PAUSED = "paused"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


_STATUS_MAP: dict[str, TaskStatus] = {
    "completed": TaskStatus.COMPLETED,
    "failed": TaskStatus.FAILED,
    "working": TaskStatus.WORKING,
    "running": TaskStatus.WORKING,
    "waiting_human": TaskStatus.INPUT_REQUIRED,
    "input_required": TaskStatus.INPUT_REQUIRED,
    "input-required": TaskStatus.INPUT_REQUIRED,
    "canceled": TaskStatus.CANCELED,
    "cancelled": TaskStatus.CANCELED,
}


def coerce_status(value: str | TaskStatus | None) -> TaskStatus | None:
    """Normalise a string or TaskStatus into a TaskStatus, or None."""
    if value is None:
        return None
    if isinstance(value, TaskStatus):
        return value
    return _STATUS_MAP.get(str(value), TaskStatus.COMPLETED)


@dataclass
class AgentCard:
    """Agent 能力名片：声明角色、工具、协议，供委派路由使用。"""

    agent_id: str
    role: str
    capabilities: list[str]
    tools_exposed: list[str] = field(default_factory=list)
    protocols_supported: list[DelegationProtocol] = field(
        default_factory=lambda: [DelegationProtocol.INTERNAL]
    )
    endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamMessage:
    """跨 Agent 通信消息载体。"""

    message_id: str
    from_agent_id: str
    to_agent_id: str | None
    task_id: str
    status: TaskStatus
    payload: Any
    created_at: datetime = field(default_factory=utc_now)
