"""PlanProposal review port (ADR-0199 §4 / P4-06).

Per ADR-0199 §4 the self-improving loop is:

    Observe fold -> PlanProposal -> Profile Resolve -> Graph Compile ->
    Validation -> Review/Approval -> Activate(new plan_ref)

This module defines the REVIEW/approval seam — the protocol between
the :class:`~lca.contracts.runtime.plan_proposal.PlanProposal` submitter
and the policy gate (0067 Artifact gate, 0093 control plane, or human
approval).

Per I-HPC-10: NO auto-activate. Implementations of this Protocol MUST
NOT mutate the active ``plan_ref``. The contract is intentionally
Protocol-only; concrete implementations land in 0187 evolve (per
ADR-0200 §3.1).

The Protocol is ``runtime_checkable`` so test stubs can satisfy it via
structural typing without inheritance.

Defined as pure data in the ``contracts`` layer: no I/O, no env reads,
no logging, no imports from ``lca.harness``, ``lca.application``,
``lca.infrastructure``, ``lca.cognition``, ``lca.runtime``,
``lca.agent`` or ``lca.plugins``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.runtime.plan_proposal import PlanProposal, ProposalStatus


@runtime_checkable
class ProposalReviewPort(Protocol):
    """The single seam where ``PlanProposal``s are reviewed (ADR-0199 P4-06).

    Implementations of this Protocol are the decision authority that
    transitions a proposal from ``draft`` / ``reviewing`` into a terminal
    accept or reject state:

      - 0067 Artifact gate (auto policy check)
      - 0093 control plane (cron-triggered review)
      - 0187 evolve (human-in-the-loop)

    Per I-HPC-10: review MUST produce an explicit decision (accept /
    reject) — no implicit default. Implementations MUST emit an
    observable audit event recording who/what decided and on what
    grounds, so the review trail is replayable alongside the durable
    run facts.
    """

    async def review(self, proposal: PlanProposal) -> ProposalReviewDecision:
        """Review a proposal and return an explicit decision.

        Per I-HPC-10: the proposal is NOT mutated by review. The decision
        carries the status transition (``draft`` / ``reviewing`` →
        ``accepted`` / ``rejected``). Activating an accepted proposal
        produces a NEW ``plan_ref``; the active ``plan_ref`` is never
        re-bound by review.

        Implementations MUST emit an observable audit event (via the
        event catalog) recording who/what decided and on what grounds
        — the decision alone is not sufficient for replayability.
        """
        ...


class ProposalReviewDecision:
    """The result of a review (ADR-0199 P4-06).

    This is a plain class (not a ``@dataclass``) so future PRs can
    extend it with rationale / reviewer metadata without breaking
    consumers — the constructor signature is the source of truth, not
    a frozen field set. Instances are value-equal on
    ``(proposal_ref, new_status, rationale, reviewer)`` and hashable
    so they can be cached / deduplicated downstream.
    """

    def __init__(
        self,
        *,
        proposal_ref: str,
        new_status: ProposalStatus,
        rationale: str = "",
        reviewer: str = "anonymous",
    ) -> None:
        self.proposal_ref = proposal_ref
        self.new_status = new_status
        self.rationale = rationale
        self.reviewer = reviewer

    def __repr__(self) -> str:
        return (
            f"ProposalReviewDecision(proposal_ref={self.proposal_ref!r}, "
            f"new_status={self.new_status!r}, reviewer={self.reviewer!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProposalReviewDecision):
            return NotImplemented
        return (
            self.proposal_ref == other.proposal_ref
            and self.new_status == other.new_status
            and self.rationale == other.rationale
            and self.reviewer == other.reviewer
        )

    def __hash__(self) -> int:
        return hash((self.proposal_ref, self.new_status, self.rationale, self.reviewer))


__all__ = ("ProposalReviewDecision", "ProposalReviewPort")
