"""EventRecord — single append-only truth unit per ADR-0165 / ADR-0165.1.

I12 enforces schema: every emitted event MUST carry enough auto-source
fields to be audit-grade without business code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from lca.contracts.observability.outcome import Outcome
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS

__all__ = ["Channel", "EventRecord", "Outcome", "Phase"]

Channel = Literal["fact", "control", "error", "diagnostic"]
Phase = Literal["live", "orphan"]


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Atomic unit of a Spine event."""

    execution_point: str
    channel: Channel
    span_id: str
    parent_span_id: str | None
    sequence: int
    epoch: int
    causality_id: str
    outcome: Outcome | None
    when: datetime
    when_corrected: datetime
    prev_event_hash: str | None
    run_id: str
    step_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    # Optional — used by PR-6 orphan semantics
    phase: Phase = "live"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.execution_point not in EXECUTION_POINTS:
            raise ValueError(
                f"UnknownExecutionPoint({self.execution_point!r}): "
                f"not in EXECUTION_POINTS whitelist"
            )
        if self.phase == "orphan" and not self.reason:
            raise ValueError("orphan events MUST carry reason (close enum; see ADR-0165.1 §19)")
        if self.sequence <= 0:
            raise ValueError(f"sequence must be > 0, got {self.sequence}")
        if self.epoch <= 0:
            raise ValueError(f"epoch must be > 0, got {self.epoch}")
