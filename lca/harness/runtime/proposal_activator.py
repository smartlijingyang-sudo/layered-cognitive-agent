"""PlanProposal activation closure (ADR-0199 §4 / P4-04 + I-HPC-10).

Per ADR-0199 §4 the self-improving loop activates a PlanProposal through:

    Observe fold -> PlanProposal -> Profile Resolve -> Graph Compile ->
    Validation -> Review/Approval -> Activate(new plan_ref)

Per I-HPC-10: activation produces a NEW ``plan_ref``; the active
``plan_ref`` is NEVER mutated. Old activations remain bound to their
old ``plan_ref``; new activations bind to the proposal's
``candidate_plan_ref``.

This module provides the pure-function activation seam:

    activate_proposal(proposal, *, session_id, profile_path, graph_ref,
                      plugin_set_ref, compiled_plan=None)
        -> SessionActivation

The seam does NOT touch the kernel, the cordis Context, or
``Session.append``. It is a pure projection: proposal + session metadata
-> activation closure. The actual K3 boot / run dispatch is the
``RuntimeFacade``'s job (P1-09 / P1-10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.plan_proposal import PlanProposal
from lca.contracts.runtime.trust import EMPTY_TRUST_ENVELOPE
from lca.harness.runtime.activation_ref import compute_activation_ref

if TYPE_CHECKING:
    from lca.contracts.protocols.state.plan import CompiledRunPlan

__all__ = (
    "ProposalActivationError",
    "activate_proposal",
    "is_proposal_activatable",
)


class ProposalActivationError(RuntimeError):
    """Raised when activation inputs are inconsistent.

    Used by :func:`activate_proposal` to reject empty / missing required
    metadata before a fresh ``SessionActivation`` is constructed.
    """


def activate_proposal(
    proposal: PlanProposal,
    *,
    session_id: str,
    profile_path: str,
    graph_ref: str,
    plugin_set_ref: str,
    compiled_plan: CompiledRunPlan | None = None,
) -> SessionActivation:
    """Close the loop: activate a PlanProposal into a fresh SessionActivation.

    Per I-HPC-10: returns a NEW ``SessionActivation``. The proposal is
    not mutated. The new ``activation_ref`` is derived from
    ``(candidate_plan_ref, graph_ref, plugin_set_ref, session_id)`` via
    :func:`compute_activation_ref` (C8 deterministic).

    The ``plan_ref`` carried by the new activation is the proposal's
    ``candidate_plan_ref`` — the new ``plan_ref`` produced by this PR.
    The previous activation, if any, remains bound to its own
    ``plan_ref``; nothing here mutates an active plan.

    Policy gate checks on the proposal's lifecycle status (e.g.
    rejecting ``draft`` / ``reviewing`` / ``rejected`` proposals) are
    the responsibility of the upstream review port (P4-06); this
    function is the pure projection step. Callers may pre-check with
    :func:`is_proposal_activatable`.

    Args:
        proposal: The :class:`PlanProposal` to activate. Read-only; not
            mutated by this function.
        session_id: The session under which the new plan will run.
        profile_path: The resolved profile path.
        graph_ref: The phase graph hash for the new plan.
        plugin_set_ref: The plugin set hash for the new plan.
        compiled_plan: Optional read-only reference to the freshly
            compiled plan; kept on the activation for callers that need
            the full plan without re-compiling.

    Returns:
        A fresh :class:`SessionActivation` bound to the proposal's
        ``candidate_plan_ref``.

    Raises:
        ProposalActivationError: If any required metadata is empty /
            missing; the activation is refused rather than produced
            with sentinel values that could later mis-route durable
            events (I-HPC-3).
    """
    if not session_id:
        raise ProposalActivationError("session_id must be non-empty")
    if not profile_path:
        raise ProposalActivationError("profile_path must be non-empty")
    if not graph_ref:
        raise ProposalActivationError("graph_ref must be non-empty")
    if not plugin_set_ref:
        raise ProposalActivationError("plugin_set_ref must be non-empty")

    # C8: deterministic; per I-HPC-10 the new activation is bound to its
    # own plan_ref (the proposal's candidate_plan_ref), not the
    # proposal's source activation_ref.
    activation_ref = compute_activation_ref(
        plan_ref=proposal.candidate_plan_ref,
        graph_ref=graph_ref,
        plugin_set_ref=plugin_set_ref,
        session_id=session_id,
    )

    return SessionActivation(
        activation_ref=activation_ref,
        plan_ref=proposal.candidate_plan_ref,
        graph_ref=graph_ref,
        plugin_set_ref=plugin_set_ref,
        profile_path=profile_path,
        session_id=session_id,
        trust_envelope=EMPTY_TRUST_ENVELOPE,
        compiled_plan=compiled_plan,
    )


def is_proposal_activatable(proposal: PlanProposal) -> bool:
    """Return ``True`` iff the proposal is in an activatable lifecycle state.

    Per the lifecycle closed set (P4-03): only ``"accepted"`` and
    ``"activated"`` are activatable. ``"draft"`` / ``"reviewing"`` need
    policy approval first; ``"rejected"`` / ``"superseded"`` / ``"expired"``
    are terminal and non-activatable.

    Note: ``"activated"`` is itself a terminal status. The intent here
    is "may this proposal be the input to an activation closure?" — a
    re-activation of a previously-activated proposal is a policy choice,
    not something this predicate forbids (the closure is pure; it does
    not consult state). Callers that need strict single-activation
    semantics should pair this predicate with their own idempotency
    check keyed on ``plan_ref``.
    """
    return proposal.status in ("accepted", "activated")
