"""Control-plane turn summary contract (ADR-0191 Wave C).

``ControlTurnView`` is the typed view DTO that gates consume exclusively
(Wave C1 closure). It is folded from durable ``turn.control.v1`` Session
facts or projected from ``AgentState.control_turns``; both producers yield
the same shape so gates never fork on source.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ControlTurnView"]


@dataclass(frozen=True, slots=True)
class ControlTurnView:
    """Gate-facing turn summary folded from durable Session facts."""

    action_type: str
    tool_name: str | None = None
    observation_success: bool | None = None
    tool_arguments: dict[str, object] | None = None
    observation_payload: object | None = None
    observation_error: str | None = None
    files_created: tuple[str, ...] = ()
