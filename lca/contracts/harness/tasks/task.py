"""Durable task and step lifecycle contracts for the session spine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StepStatus(StrEnum):
    """Explicit lifecycle states for one executable task step."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TaskStep:
    """Immutable step snapshot suitable for journal/checkpoint persistence."""

    task_id: str
    step_id: str
    node_ref: str
    status: StepStatus = StepStatus.PENDING
    attempt: int = 0
    input_ref: str | None = None
    output_ref: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.step_id.strip() or not self.node_ref.strip():
            raise ValueError("task_id, step_id and node_ref must not be empty")
        if self.attempt < 0:
            raise ValueError("step attempt must be non-negative")
        if self.status is StepStatus.SUCCEEDED and self.error_code:
            raise ValueError("succeeded step cannot carry an error code")


__all__ = ["StepStatus", "TaskStep"]
