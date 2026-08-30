"""Cooperative cancellation contract for long-running Agent tasks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CancellationState(StrEnum):
    REQUESTED = "requested"
    APPLIED = "applied"
    IGNORED = "ignored"


@dataclass(frozen=True)
class CancellationRequest:
    task_id: str
    reason: str
    state: CancellationState = CancellationState.REQUESTED

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.reason.strip():
            raise ValueError("cancellation task_id and reason must not be empty")

    def apply(self) -> CancellationRequest:
        return CancellationRequest(self.task_id, self.reason, CancellationState.APPLIED)


__all__ = ["CancellationRequest", "CancellationState"]
