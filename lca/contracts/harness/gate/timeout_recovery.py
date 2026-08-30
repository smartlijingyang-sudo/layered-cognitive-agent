"""Deterministic timeout recovery policy for long-running Agent steps."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TimeoutAction(StrEnum):
    RETRY = "retry"
    RESUME = "resume"
    FAIL = "fail"


@dataclass(frozen=True)
class TimeoutRecoveryPolicy:
    max_retries: int = 2
    resume_from_checkpoint: bool = True

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

    def decide(self, retry_count: int, checkpoint_available: bool) -> TimeoutAction:
        if retry_count < self.max_retries:
            return TimeoutAction.RETRY
        if self.resume_from_checkpoint and checkpoint_available:
            return TimeoutAction.RESUME
        return TimeoutAction.FAIL


__all__ = ["TimeoutAction", "TimeoutRecoveryPolicy"]
