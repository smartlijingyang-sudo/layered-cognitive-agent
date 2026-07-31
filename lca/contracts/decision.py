"""Decision / Observation / Reflection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lca.contracts.enums import ContentType, DelegationProtocol, ReflectionVerdict
from lca.contracts.lifecycle import AgentCard

__all__ = [
    "AgentCard",
    "Decision",
    "DelegationSpec",
    "Observation",
    "Reflection",
    "ToolCall",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ToolCall:
    """Single tool invocation: name + arguments + optional idempotency key."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: str | None = None
    timeout_s: int | None = None


@dataclass
class DelegationSpec:
    """Ask a teammate: target role/agent + protocol + optional deadline."""

    subtask: str
    target_role: str | None = None
    target_agent_id: str | None = None
    target_agent_card: AgentCard | None = None
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    protocol: DelegationProtocol = DelegationProtocol.INTERNAL


@dataclass
class Decision:
    """One step's chosen action: type + rationale + tool calls / delegation."""

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
    """Outcome of acting on a Decision (tool / delegate / respond)."""

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

    @property
    def ok(self) -> bool:
        return self.success

    @property
    def data(self) -> Any:
        return self.payload


@dataclass
class Reflection:
    """Critic output: verdict + lesson + optional correction Decision."""

    reflection_id: str
    verdict: ReflectionVerdict
    lesson: str | None = None
    correction: Decision | None = None
    extra: dict[str, Any] = field(default_factory=dict)
