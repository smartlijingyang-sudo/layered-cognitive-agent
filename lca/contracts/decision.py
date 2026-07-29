"""第5.4节：决策与执行契约 + 第5.7节：任务生命周期与跨 Agent 通信契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from lca.contracts.enums import ContentType, DelegationProtocol, ReflectionVerdict


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 任务生命周期 ──────────────────────────────────────────────────


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    PAUSED = "paused"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# ── Agent 身份卡 ──────────────────────────────────────────────────


@dataclass
class AgentCard:
    agent_id: str
    role: str
    capabilities: list[str]
    tools_exposed: list[str] = field(default_factory=list)
    protocols_supported: list[DelegationProtocol] = field(
        default_factory=lambda: [DelegationProtocol.INTERNAL]
    )
    endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ── 决策与执行 ────────────────────────────────────────────────────


@dataclass
class ToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: str | None = None
    timeout_s: int | None = None


@dataclass
class DelegationSpec:
    subtask: str
    target_role: str | None = None
    target_agent_id: str | None = None
    target_agent_card: AgentCard | None = None
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    protocol: DelegationProtocol = DelegationProtocol.INTERNAL


@dataclass
class StructuredDecision:
    decision_id: str
    action_type: str
    rationale: str
    confidence: float
    tool_calls: list[ToolCall] = field(default_factory=list)
    delegate_to: DelegationSpec | None = None
    response_text: str | None = None
    schema_version: str = "1.0"
    created_at: datetime = field(default_factory=_now)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    observation_id: str
    success: bool
    payload: Any
    content_type: ContentType = ContentType.TEXT
    tool_call_id: str | None = None
    error: str | None = None
    retries_used: int = 0
    latency_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Reflection:
    reflection_id: str
    verdict: ReflectionVerdict
    lesson: str | None = None
    correction: StructuredDecision | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ── 团队消息 ──────────────────────────────────────────────────────


@dataclass
class TeamMessage:
    message_id: str
    from_agent_id: str
    to_agent_id: str | None
    task_id: str
    status: TaskStatus
    payload: Any
    created_at: datetime = field(default_factory=_now)
