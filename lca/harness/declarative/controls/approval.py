"""Replayable approval state machine for the declarative execution seam."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from time import time
from typing import Any


class ApprovalState(str, Enum):
    """Durable states for one human approval request."""

    REQUESTED = "requested"
    WAITING_INPUT = "waiting_input"
    APPROVED = "approved"
    DENIED = "denied"
    RESUMED = "resumed"
    EFFECT_COMPLETED = "effect_completed"
    EFFECT_DENIED = "effect_denied"


@dataclass(frozen=True, slots=True)
class ApprovalTransition:
    """A replayable state transition with no live object references."""

    approval_id: str
    event: str
    previous: ApprovalState | None
    current: ApprovalState
    sequence: int
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ApprovalRequestSnapshot:
    """Durable approval metadata used by pause/resume adapters."""

    approval_id: str
    task_id: str
    expires_at: float
    requested_scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.approval_id.strip() or not self.task_id.strip():
            raise ValueError("approval and task IDs must not be empty")
        if self.expires_at <= 0:
            raise ValueError("approval expiry must be positive")

    def is_expired(self, now: float | None = None) -> bool:
        return (time() if now is None else now) >= self.expires_at

    def ensure_active(self, now: float | None = None) -> None:
        if self.is_expired(now):
            raise ValueError(f"approval request expired: {self.approval_id}")


_EVENT_TARGETS: dict[str, tuple[ApprovalState | None, ApprovalState]] = {
    "approval.requested": (None, ApprovalState.REQUESTED),
    "approval.waiting_input": (ApprovalState.REQUESTED, ApprovalState.WAITING_INPUT),
    "approval.resolved.approved": (ApprovalState.WAITING_INPUT, ApprovalState.APPROVED),
    "approval.resolved.denied": (ApprovalState.WAITING_INPUT, ApprovalState.DENIED),
    "approval.resumed": (ApprovalState.APPROVED, ApprovalState.RESUMED),
    "effect.completed": (ApprovalState.RESUMED, ApprovalState.EFFECT_COMPLETED),
    "effect.denied": (ApprovalState.RESUMED, ApprovalState.EFFECT_DENIED),
}


class ApprovalStateMachine:
    """Fold approval facts and reject invalid or ambiguous transitions."""

    def __init__(self) -> None:
        self._states: dict[str, ApprovalState] = {}
        self._sequence = 0

    def apply(
        self,
        event: str,
        approval_id: str,
        *,
        payload: Mapping[str, Any] | None = None,
        sequence: int | None = None,
    ) -> ApprovalTransition:
        if not isinstance(event, str) or not event:
            raise ValueError("approval event must be a non-empty string")
        if not isinstance(approval_id, str) or not approval_id:
            raise ValueError("approval_id must be a non-empty string")
        expected_previous, current = _EVENT_TARGETS.get(event, (None, None))
        if current is None:
            raise ValueError(f"unknown approval event: {event}")
        previous = self._states.get(approval_id)
        if previous is not expected_previous:
            raise ValueError(
                f"invalid approval transition for {approval_id}: "
                f"{previous.value if previous else 'none'} -> {event}"
            )
        next_sequence = self._sequence + 1 if sequence is None else sequence
        if next_sequence <= self._sequence:
            raise ValueError("approval sequence must increase monotonically")
        self._sequence = next_sequence
        self._states[approval_id] = current
        return ApprovalTransition(
            approval_id=approval_id,
            event=event,
            previous=previous,
            current=current,
            sequence=next_sequence,
            payload=dict(payload or {}),
        )

    def state(self, approval_id: str) -> ApprovalState | None:
        return self._states.get(approval_id)

    @classmethod
    def replay(cls, events: Iterable[Mapping[str, Any]]) -> ApprovalStateMachine:
        machine = cls()
        for event in events:
            raw_event = event.get("event")
            raw_approval_id = event.get("approval_id")
            raw_sequence = event.get("sequence")
            if not isinstance(raw_event, str) or not raw_event:
                raise ValueError("approval replay event must have a non-empty event")
            if not isinstance(raw_approval_id, str) or not raw_approval_id:
                raise ValueError("approval replay event must have a non-empty approval_id")
            if not isinstance(raw_sequence, int) or isinstance(raw_sequence, bool):
                raise ValueError("approval replay event sequence must be an integer")
            machine.apply(
                raw_event,
                raw_approval_id,
                payload=event.get("payload") if isinstance(event.get("payload"), Mapping) else {},
                sequence=raw_sequence,
            )
        return machine


__all__ = [
    "ApprovalRequestSnapshot",
    "ApprovalState",
    "ApprovalStateMachine",
    "ApprovalTransition",
]
