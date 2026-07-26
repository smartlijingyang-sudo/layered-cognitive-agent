"""第5.7节：任务生命周期与跨 Agent 通信契约。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class AgentCard:
    agent_id: str
    role: str
    capabilities: list[str]
    tools_exposed: list[str] = field(default_factory=list)
    protocols_supported: list[Literal["internal", "a2a", "mcp"]] = field(default_factory=lambda: ["internal"])
    endpoint: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamMessage:
    message_id: str
    from_agent_id: str
    to_agent_id: Optional[str]
    task_id: str
    status: TaskStatus
    payload: Any
    created_at: datetime = field(default_factory=_now)
