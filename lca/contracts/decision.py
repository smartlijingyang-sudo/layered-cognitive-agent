"""Decision / Observation / Reflection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lca.contracts.enums import ContentType, DelegationProtocol, ReflectionVerdict
from lca.contracts.ids import utc_now
from lca.contracts.lifecycle import AgentCard

if TYPE_CHECKING:
    from lca.contracts.result import Result

__all__ = [
    "AgentCard",
    "Decision",
    "DelegationSpec",
    "Observation",
    "Reflection",
    "ToolCall",
]


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
    """One step's chosen action: type + rationale + tool calls / delegation.

    ``delegations`` is the sole representation of DELEGATE/HANDOFF targets:
    empty = none, one entry = single target, multiple = fan-out.
    """

    decision_id: str
    action_type: str
    rationale: str
    confidence: float
    tool_calls: list[ToolCall] = field(default_factory=list)
    delegations: list[DelegationSpec] = field(default_factory=list)
    response_text: str | None = None
    schema_version: str = "1.0"
    created_at: datetime = field(default_factory=utc_now)
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

    @classmethod
    def from_result(cls, result: Result) -> Observation:
        """Bridge a Result back into an Observation for channel return path."""
        from lca.contracts.lifecycle import TaskStatus

        return cls(
            observation_id=f"obs_{result.trace_id}",
            success=result.status == TaskStatus.COMPLETED,
            payload=result.output,
            error=result.error,
            extra={
                "source_trace_id": result.trace_id,
                "source_total_steps": result.total_steps,
                "source_status": result.status,
            },
        )


@dataclass
class Reflection:
    """Critic output: verdict + lesson + optional correction Decision."""

    reflection_id: str
    verdict: ReflectionVerdict
    lesson: str | None = None
    correction: Decision | None = None
    extra: dict[str, Any] = field(default_factory=dict)
