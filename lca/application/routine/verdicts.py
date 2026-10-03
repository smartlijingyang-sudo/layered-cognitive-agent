"""Explicit trigger verdicts for routine scheduling (ADR-0263 C3).

Replaces the silent ``can_trigger() -> False`` with an observable verdict:
*why* a routine did not run is queryable (journal/spine留痕 happens in the
tick driver, ADR-0263 §10 — deferred). A SKIP never retries and never queues;
the next tick re-evaluates from scratch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SkipReason(StrEnum):
    """Why a routine trigger was skipped (ADR-0263 C3)."""

    ALREADY_RUNNING = "already_running"
    BUDGET_EXCEEDED = "budget_exceeded"
    NOT_DUE = "not_due"
    DISABLED = "disabled"


@dataclass(frozen=True)
class TriggerDecision:
    """Verdict of one trigger evaluation (ADR-0263 §8).

    ``allowed=True`` always pairs with ``skip_reason=None``; a skip always
    names its reason. No other combination is representable.
    """

    allowed: bool
    skip_reason: SkipReason | None = None

    def __post_init__(self) -> None:
        if self.allowed and self.skip_reason is not None:
            raise ValueError("allowed decision must not carry a skip_reason")
        if not self.allowed and self.skip_reason is None:
            raise ValueError("skipped decision must name a skip_reason")


__all__ = ["SkipReason", "TriggerDecision"]
