"""decision contracts - no lifecycle twins."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lca.contracts.enums import ContentType, DelegationProtocol, ReflectionVerdict
from lca.contracts.lifecycle import AgentCard

__all__ = [
    "AgentCard",
    "DelegationSpec",
    "Observation",
    "Reflection",
    "StructuredDecision",
    "ToolCall",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ToolCall:
    """单次工具调用请求：工具名 + 参数 + 幂等键。"""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: str | None = None
    timeout_s: int | None = None


@dataclass
class DelegationSpec:
    """委派规格：目标角色/Agent + 传输协议 + 截止时间。"""

    subtask: str
    target_role: str | None = None
    target_agent_id: str | None = None
    target_agent_card: AgentCard | None = None
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    protocol: DelegationProtocol = DelegationProtocol.INTERNAL


@dataclass
class StructuredDecision:
    """Agent 单步决策输出：行动类型 + 理由 + 工具调用 / 委派规格。"""

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
    """工具执行 / 委派结果：成功标志 + 载荷 + 降级信息。"""

    observation_id: str
    success: bool
    payload: Any
    content_type: ContentType = ContentType.TEXT
    tool_call_id: str | None = None
    error: str | None = None
    retries_used: int = 0
    latency_ms: int = 0
    degraded_from: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Reflection:
    """Critic 自省输出：判定 + 教训 + 可选纠正决策。"""

    reflection_id: str
    verdict: ReflectionVerdict
    lesson: str | None = None
    correction: StructuredDecision | None = None
    extra: dict[str, Any] = field(default_factory=dict)
