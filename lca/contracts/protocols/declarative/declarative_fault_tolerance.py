"""Immutable plan data for bounded phase-attempt fault tolerance."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.protocols.declarative.declarative_common import DeclarativeValidationError


@dataclass(frozen=True, slots=True)
class PhaseExecutionPolicy:
    """Plan-declared retry, timeout, and exhaustion behavior for one phase node."""

    max_attempts: int = 1
    timeout_seconds: float | None = None
    retry_on: tuple[str, ...] = ()
    initial_backoff_seconds: float = 0.0
    backoff_multiplier: float = 2.0
    on_exhausted: str = "raise"

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise DeclarativeValidationError("PG-010", "max_attempts must be positive")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise DeclarativeValidationError("PG-010", "timeout_seconds must be positive when set")
        if self.initial_backoff_seconds < 0:
            raise DeclarativeValidationError(
                "PG-010", "initial_backoff_seconds must be non-negative"
            )
        if self.backoff_multiplier < 1:
            raise DeclarativeValidationError("PG-010", "backoff_multiplier must be at least one")
        if self.on_exhausted not in {"raise", "route_to_stop"}:
            raise DeclarativeValidationError(
                "PG-010", "on_exhausted must be raise or route_to_stop"
            )
        if not isinstance(self.retry_on, tuple):
            object.__setattr__(self, "retry_on", tuple(str(item) for item in self.retry_on))
        unsupported = set(self.retry_on).difference({"timeout", "transient"})
        if unsupported:
            raise DeclarativeValidationError(
                "PG-010", "retry_on supports only timeout and transient categories"
            )


__all__ = ["PhaseExecutionPolicy"]
