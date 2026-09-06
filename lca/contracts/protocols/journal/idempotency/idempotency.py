"""Durable effect idempotency contract (ADR-0075 / full-plugin-remediation §5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

ClaimStatus = Literal["new", "completed", "in_progress"]


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    """Result of atomically claiming an effect key for one compiled plan."""

    status: ClaimStatus
    receipt: object | None = None


@runtime_checkable
class IdempotencyStore(Protocol):
    """Durable claim/receipt store for effect execution.

    Implementations must make ``claim(plan_ref, idempotency_key)`` atomic across
    concurrent callers and process restarts. A claim remains ``in_progress``
    until ``complete`` commits a receipt; a later claim of that key must then
    fail closed as an uncertain effect rather than reissuing the side effect.
    """

    async def claim(self, plan_ref: str, idempotency_key: str) -> IdempotencyClaim: ...

    async def complete(self, plan_ref: str, idempotency_key: str, receipt: object) -> None: ...


__all__ = ["ClaimStatus", "IdempotencyClaim", "IdempotencyStore"]
