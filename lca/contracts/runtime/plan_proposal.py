"""PlanProposal contract (ADR-0199 §4 / P4-03 + I-HPC-10).

Per ADR-0199 §4 the self-improving loop produces ``PlanProposal``s:

    Observe fold -> PlanProposal -> Profile Resolve -> Graph Compile
    -> Validation -> Review/Approval -> Activate(new plan_ref)

Per I-HPC-10: a ``PlanProposal`` is **immutable**. Activating it produces a
new ``plan_ref`` (never re-binding the active ``plan_ref``). This invariant
protects running activations from being silently mutated by self-improvement.

The proposal carries:

- ``proposal_ref``: hash of (source_activation_ref, candidate_plan_ref,
  proposed_changes) — the SSOT key for the proposal (C8 determinism).
- ``source_activation_ref``: the activation that originated the proposal
  (for traceability / "fork read-only main Spine").
- ``candidate_plan_ref``: the ``plan_ref`` the proposal would produce IF
  activated (does not yet exist; produced by the compile closure PR P4-04).
- ``proposed_changes``: sorted ``(key, value)`` pairs describing the diff
  payload (opaque dict — final shape is fixed by the evolution policy in a
  future PR; the contract here only commits to determinism + immutability).
- ``status``: lifecycle state of the proposal. Per I-HPC-10, once a
  proposal reaches a terminal state its ``plan_ref`` is bound; transitions
  are made by emitting a new proposal instance, not by mutating this one.

Defined as pure data in the ``contracts`` layer: no I/O, no env reads,
no logging, no imports from ``lca.harness``, ``lca.application``,
``lca.infrastructure``, ``lca.cognition``, ``lca.runtime``, ``lca.agent``
or ``lca.plugins``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from lca.contracts.observability.canonical_digest import canonical_digest

ProposalStatus = Literal[
    "draft",  # proposal created, not yet reviewed
    "reviewing",  # under review (human or policy gate)
    "accepted",  # approved, awaiting activation
    "rejected",  # denied by review
    "activated",  # activation complete (terminal)
    "superseded",  # replaced by a newer proposal (terminal)
    "expired",  # exceeded TTL (terminal)
]
"""Closed set of proposal lifecycle states (ADR-0199 P4-03 + I-HPC-10).

Per I-HPC-10: once a proposal reaches a terminal state, its ``plan_ref``
is bound; transitions are made by emitting a new proposal instance, not
by mutating the existing one.
"""

_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"activated", "rejected", "superseded", "expired"}
)
"""Statuses considered terminal for ``PlanProposal.is_terminal()`` (I-HPC-10).

A terminal status signals that the proposal's ``candidate_plan_ref`` is
either bound (activated) or will never be bound (rejected / superseded /
expired). New lifecycle steps require a fresh ``PlanProposal`` instance.
"""

_PROPOSAL_HASH_NAMESPACE: Final[str] = "lca.plan_proposal.v1"
"""Content-addressed namespace for ``proposal_ref`` (C8 determinism).

The namespace prefix guards against collisions with other content-addressed
identifiers in the same string-typed keyspace (activation_ref, plan_ref,
graph_ref, plugin_set_ref). The ``v1`` suffix is part of the contract:
any future change to the canonicalized payload MUST bump the version to
preserve C8 determinism across re-emission of historical proposals.
"""


@dataclass(frozen=True, slots=True)
class PlanProposal:
    """Immutable candidate for the next plan activation (ADR-0199 P4-03).

    Per I-HPC-10: once created, a proposal's fields cannot change. Lifecycle
    transitions are expressed by creating a NEW proposal (e.g., with status
    transitioning from ``draft`` -> ``accepted``). The active ``plan_ref``
    is NEVER mutated by proposal activation; activation produces a new
    ``plan_ref`` (handed back as ``candidate_plan_ref`` here, but only
    after P4-04 wires the compile closure).

    ``proposal_ref`` is the SSOT key for the proposal; it is derived from
    the canonical JSON of ``(source_activation_ref, candidate_plan_ref,
    proposed_changes)`` (C8: same content -> same ref).
    """

    proposal_ref: str
    source_activation_ref: str
    candidate_plan_ref: str
    proposed_changes: tuple[tuple[str, str], ...]
    status: ProposalStatus = "draft"
    rationale: str = ""
    created_at_seq: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_ref, str) or not self.proposal_ref:
            raise ValueError("PlanProposal.proposal_ref must be a non-empty string")
        if not isinstance(self.source_activation_ref, str) or not self.source_activation_ref:
            raise ValueError("PlanProposal.source_activation_ref must be a non-empty string")
        if not isinstance(self.candidate_plan_ref, str) or not self.candidate_plan_ref:
            raise ValueError("PlanProposal.candidate_plan_ref must be a non-empty string")
        if not isinstance(self.proposed_changes, tuple) or not all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and isinstance(pair[0], str)
            and isinstance(pair[1], str)
            for pair in self.proposed_changes
        ):
            raise TypeError("PlanProposal.proposed_changes must be a tuple of (str, str) pairs")
        if self.status not in (
            "draft",
            "reviewing",
            "accepted",
            "rejected",
            "activated",
            "superseded",
            "expired",
        ):
            raise ValueError(f"PlanProposal.status invalid: {self.status!r}")
        if not isinstance(self.rationale, str):
            raise TypeError("PlanProposal.rationale must be a str")
        if not isinstance(self.created_at_seq, int) or isinstance(self.created_at_seq, bool):
            raise TypeError("PlanProposal.created_at_seq must be an int")
        if self.created_at_seq < 0:
            raise ValueError("PlanProposal.created_at_seq must be >= 0")

    def is_terminal(self) -> bool:
        """Return ``True`` if this proposal has reached a terminal state.

        Terminal states (``activated`` / ``rejected`` / ``superseded`` /
        ``expired``) signal that the proposal's ``candidate_plan_ref`` is
        bound or will never be bound. New lifecycle steps require a fresh
        ``PlanProposal`` instance (I-HPC-10).
        """
        return self.status in _TERMINAL_STATUSES


def compute_proposal_ref(
    *,
    source_activation_ref: str,
    candidate_plan_ref: str,
    proposed_changes: Mapping[str, Any] | None = None,
) -> str:
    """Compute a deterministic ``proposal_ref`` for the proposal contents.

    Per C8: deterministic; same inputs -> same ref.
    Per I-HPC-10: changing ANY input changes the ref (no shadow rewriting).

    The canonical form sorts keys so insertion order in the input mapping
    does not affect the digest. ``None`` is treated as an empty mapping.
    """
    payload: dict[str, Any] = {
        "candidate_plan_ref": candidate_plan_ref,
        "proposed_changes": dict(proposed_changes) if proposed_changes else {},
        "source_activation_ref": source_activation_ref,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return canonical_digest(
        canonical,
        length=64,
        prefix=f"{_PROPOSAL_HASH_NAMESPACE}:",
    )


def build_proposal(
    *,
    source_activation_ref: str,
    candidate_plan_ref: str,
    proposed_changes: Mapping[str, Any] | None = None,
    rationale: str = "",
    status: ProposalStatus = "draft",
    created_at_seq: int = 0,
) -> PlanProposal:
    """Construct a ``PlanProposal`` with auto-computed ``proposal_ref``.

    Per C8: ``proposal_ref`` is derived from the canonical JSON of inputs
    (see :func:`compute_proposal_ref`).

    ``proposed_changes`` is stored as a sorted tuple of ``(key, value)``
    string pairs to preserve determinism while supporting arbitrary change
    payloads. Non-string values are accepted for hashing only — the
    dataclass field is constrained to ``tuple[tuple[str, str], ...]`` so
    callers that want the proposal stored long-term must stringify the
    payload at proposal time (e.g., ``json.dumps(change)``). ``None`` is
    treated as an empty mapping.
    """
    changes_mapping: Mapping[str, Any] = proposed_changes if proposed_changes is not None else {}
    proposal_ref = compute_proposal_ref(
        source_activation_ref=source_activation_ref,
        candidate_plan_ref=candidate_plan_ref,
        proposed_changes=changes_mapping,
    )
    sorted_changes = tuple((str(key), str(value)) for key, value in sorted(changes_mapping.items()))
    return PlanProposal(
        proposal_ref=proposal_ref,
        source_activation_ref=source_activation_ref,
        candidate_plan_ref=candidate_plan_ref,
        proposed_changes=sorted_changes,
        status=status,
        rationale=rationale,
        created_at_seq=created_at_seq,
    )


__all__ = (
    "PlanProposal",
    "ProposalStatus",
    "build_proposal",
    "compute_proposal_ref",
)
