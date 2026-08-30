"""Event-sourced idempotency decisions for durable Session commands.

The Session Spine keeps durable facts in ``SessionStore``.  A command ledger is
therefore a pure policy over that fact stream, rather than a second mutable
cache.  Profiles may replace the policy when they use a database event store or
need stricter command-audit semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from lca.contracts.harness.session import SessionEvent


class ApprovalResumeDisposition(StrEnum):
    """The only replay-safe outcomes for an approval-resume command."""

    PROCEED = "proceed"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ApprovalResumeDecision:
    """A durable decision derived from immutable Session facts.

    ``REPLAY`` means the same command has already produced a terminal Session
    checkpoint and its original accepted sequence can be returned without
    re-entering the Agent Loop.  ``CONFLICT`` preserves single-resolution
    semantics for an approval and must be rejected by the command router.
    """

    disposition: ApprovalResumeDisposition
    receipt_seq: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition is ApprovalResumeDisposition.REPLAY and self.receipt_seq is None:
            raise ValueError("replay decisions require the original receipt sequence")
        if (
            self.disposition is not ApprovalResumeDisposition.REPLAY
            and self.receipt_seq is not None
        ):
            raise ValueError("only replay decisions may expose a receipt sequence")
        if self.disposition is ApprovalResumeDisposition.CONFLICT and not self.reason:
            raise ValueError("conflict decisions require a stable rejection reason")


@runtime_checkable
class SessionCommandLedger(Protocol):
    """Derive a durable approval-resume decision from one Session's facts."""

    def decide_approval_resume(
        self,
        events: tuple[SessionEvent, ...],
        *,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> ApprovalResumeDecision: ...


__all__ = [
    "ApprovalResumeDecision",
    "ApprovalResumeDisposition",
    "SessionCommandLedger",
]
