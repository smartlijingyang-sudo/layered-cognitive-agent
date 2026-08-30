"""Compensation contract for side-effecting Agent actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompensationPlan:
    operation: str
    compensation_operation: str
    idempotency_key: str
    eligible: bool = True

    def __post_init__(self) -> None:
        if not self.operation.strip() or not self.compensation_operation.strip():
            raise ValueError("compensation operations must not be empty")
        if not self.idempotency_key.strip():
            raise ValueError("compensation requires an idempotency key")

    def can_compensate(self) -> bool:
        return self.eligible and self.operation != self.compensation_operation


__all__ = ["CompensationPlan"]
