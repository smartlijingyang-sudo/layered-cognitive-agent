"""Control-plane state fold contracts (ADR-0191 Wave C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ControlState:
    """JSON-serializable control-plane snapshot (not model wire)."""

    turn_count: int = 0
    last_action_type: str | None = None
    last_tool_name: str | None = None
    last_success: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ControlStateFolder(Protocol):
    """Fold Session facts into control-plane state."""

    def fold(self, session: Any) -> ControlState:
        """Build control state from a SessionReader / snapshot."""
        ...


__all__ = ["ControlState", "ControlStateFolder"]
