"""Decision / Observation / Reflection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.enums import ContentType, DelegationProtocol, ReflectionVerdict
from lca.contracts.atoms.ids import utc_now
from lca.contracts.models.core.lifecycle import AgentCard

if TYPE_CHECKING:
    from lca.contracts.models.core.result import Result

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
    """Ask a teammate: target role/agent + protocol + optional deadline/timeout.

    资源切片优先级（ADR-0049）：``timeout_s`` > ``deadline`` 剩余 >
    父 RunBudget 剩余与 ``DEFAULT_DELEGATION_TIMEOUT_S`` 的解析结果。
    """

    subtask: str
    target_role: str | None = None
    target_agent_id: str | None = None
    target_agent_card: AgentCard | None = None
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    timeout_s: float | None = None
    protocol: DelegationProtocol = DelegationProtocol.INTERNAL


@dataclass
class Decision:
    """One step's chosen action: type + rationale + tool calls / delegation.

    ``delegations`` is the sole representation of DELEGATE/HANDOFF targets:
    empty = none, one entry = single target, multiple = fan-out.

    ``degraded_from`` records the original ``action_type`` when the decision
    was rewritten by the anti-corruption layer (see ``DegradationPolicy``);
    ``None`` means the decision is native. Provenance flows Decision →
    Observation so hooks and stop policies can see the degradation.
    """

    decision_id: str
    action_type: str
    rationale: str
    confidence: float
    tool_calls: list[ToolCall] = field(default_factory=list)
    delegations: list[DelegationSpec] = field(default_factory=list)
    response_text: str | None = None
    degraded_from: str | None = None
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
        from lca.contracts.atoms.semantic_keys import (
            COMPLETION_EMPTY,
            COMPLETION_FULL,
            COMPLETION_PARTIAL,
            FAILURE_KIND,
            FAILURE_KIND_TRANSIENT,
            OBS_COMPLETION_QUALITY,
        )
        from lca.contracts.models.core.lifecycle import TaskStatus

        success = result.status == TaskStatus.COMPLETED
        payload = result.output
        extra: dict[str, Any] = {
            "source_trace_id": result.trace_id,
            "source_total_steps": result.total_steps,
            "source_status": result.status,
        }
        if success:
            extra[OBS_COMPLETION_QUALITY] = COMPLETION_FULL
        elif payload:
            # CANCELED / FAILED 但有 partial 正文（ADR-0049 harvest）
            extra[OBS_COMPLETION_QUALITY] = COMPLETION_PARTIAL
            extra[FAILURE_KIND] = FAILURE_KIND_TRANSIENT
        elif result.status == TaskStatus.CANCELED:
            extra[OBS_COMPLETION_QUALITY] = COMPLETION_EMPTY
            extra[FAILURE_KIND] = FAILURE_KIND_TRANSIENT
        return cls(
            observation_id=f"obs_{result.trace_id}",
            success=success,
            payload=payload,
            error=result.error,
            extra=extra,
        )


@dataclass
class Reflection:
    """Critic output: verdict + lesson + optional correction Decision."""

    reflection_id: str
    verdict: ReflectionVerdict
    lesson: str | None = None
    correction: Decision | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Turn:
    """One cognitive step: decision + act result + optional reflection."""

    decision: Decision
    observation: Observation
    reflection: Reflection | None = None
    extra: dict[str, Any] = field(default_factory=dict)
