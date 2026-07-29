"""第5.7节：任务生命周期与跨 Agent 通信契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    PAUSED = "paused"  # 新增：系统级暂停（非人工审批），区别于 INPUT_REQUIRED
    INPUT_REQUIRED = "input-required"  # 取代原来的 "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class AgentCard:
    agent_id: str
    role: str
    capabilities: list[str]
    tools_exposed: list[str] = field(default_factory=list)
    protocols_supported: list[Literal["internal", "a2a", "mcp"]] = field(
        default_factory=lambda: ["internal"]
    )
    endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamMessage:
    message_id: str
    from_agent_id: str
    to_agent_id: str | None
    task_id: str
    status: TaskStatus
    payload: Any
    created_at: datetime = field(default_factory=_now)
