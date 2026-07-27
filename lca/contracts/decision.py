"""第5.4节：决策与执行契约。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class ToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: Optional[str] = None
    timeout_s: Optional[int] = None


@dataclass
class DelegationSpec:
    subtask: str
    target_role: Optional[str] = None
    target_agent_id: Optional[str] = None
    target_agent_card: Optional[Any] = None
    context_refs: list[str] = field(default_factory=list)
    deadline: Optional[datetime] = None
    protocol: Literal["internal", "a2a", "mcp"] = "internal"


@dataclass
class StructuredDecision:
    decision_id: str
    action_type: Literal["use_tool", "delegate", "respond", "ask_human", "stop"]
    rationale: str
    confidence: float
    tool_calls: list[ToolCall] = field(default_factory=list)
    delegate_to: Optional[DelegationSpec] = None
    response_text: Optional[str] = None
    schema_version: str = "1.0"
    created_at: datetime = field(default_factory=_now)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    observation_id: str
    success: bool
    payload: Any
    content_type: Literal["text", "image", "audio", "structured"] = "text"
    tool_call_id: Optional[str] = None
    error: Optional[str] = None
    retries_used: int = 0
    latency_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Reflection:
    reflection_id: str
    verdict: Literal["on_track", "needs_correction", "blocked"]
    lesson: Optional[str] = None
    correction: Optional[StructuredDecision] = None
    extra: dict[str, Any] = field(default_factory=dict)
