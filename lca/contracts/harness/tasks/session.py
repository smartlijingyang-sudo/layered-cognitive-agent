"""Session header, event, and type registry.

Spec §2.2.2 of ``docs/specs/harness-spine-spec.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SESSION_FORMAT_VERSION = 1

_EVENT_REGISTRY: dict[str, type] = {}


@dataclass(frozen=True)
class SessionHeader:
    """Session metadata written once at create time."""

    version: int
    id: str
    created_at: int
    cwd: str | None = None
    parent_session: str | None = None
    seed_length: int | None = None
    origin: Literal["user", "subagent", "workflow"] | None = None
    delegation_depth: int | None = None
    agent_preset: str | None = None
    profile_digest: str | None = None

    def __post_init__(self) -> None:
        """Reject malformed immutable headers before they enter the journal."""
        if self.version != SESSION_FORMAT_VERSION:
            raise ValueError(f"unsupported session format version: {self.version}")
        if not self.id.strip():
            raise ValueError("session header id must not be empty")
        if self.created_at < 0:
            raise ValueError("session header created_at must be non-negative")
        if self.delegation_depth is not None and self.delegation_depth < 0:
            raise ValueError("delegation_depth must be non-negative")


@dataclass(frozen=True)
class EventScope:
    """Tracing metadata stamped from contextvars."""

    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    causation_id: str | None = None
    run_activation_id: str | None = None
    plugin_id: str | None = None
    plugin_version: str | None = None
    scope_id: str | None = None


@dataclass(frozen=True)
class SessionEvent:
    """One immutable session fact (唯一事件信封 —— kernel 层经 re-export 复用)."""

    type: str
    seq: int
    time: int
    data: dict[str, Any]
    session_id: str
    actor: str | None = None
    provider: str | None = None
    visibility: Literal["model", "audit", "internal"] = "model"
    scope: EventScope | None = None

    @property
    def category(self) -> str:
        """spine 事件形态投影：``foldRequestHeader`` 按 category 识别 fold 目标。"""
        return self.type

    @property
    def payload(self) -> dict[str, Any]:
        """spine 事件形态投影：``data`` 的只读别名。"""
        return self.data


def session_event(
    type_name: str,
    *,
    visibility: Literal["model", "audit", "internal"] = "model",
    redaction: type | None = None,
) -> Any:
    """Register a session event payload class."""

    def decorator(cls: type) -> type:
        cls._event_type = type_name  # type: ignore[attr-defined]
        cls._visibility = visibility  # type: ignore[attr-defined]
        cls._redaction = redaction  # type: ignore[attr-defined]
        _EVENT_REGISTRY[type_name] = cls
        return cls

    return decorator


def event_registry() -> dict[str, type]:
    """Read-only copy of registered event types."""
    return dict(_EVENT_REGISTRY)


def event_type_of(payload: Any) -> str:
    """Return the registered type name for a payload instance."""
    type_name = getattr(type(payload), "_event_type", None)
    if not isinstance(type_name, str) or not type_name:
        raise TypeError(f"{type(payload).__name__} is not a registered session event")
    return type_name
