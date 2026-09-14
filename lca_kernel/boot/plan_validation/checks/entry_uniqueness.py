"""Entry-uniqueness check.

The plan model validator already rejects the exact extremes
(``0 entry`` and ``N>1 entry``), but a YAML may slip through with
two nodes both marked ``entry: true`` — the Pydantic error then
loses the kernel-level intent.  This check restates the invariant
in the operator's voice and points at the offending nodes by id so
boot fails with a single, actionable message.

Only ``>1`` is reported here.  ``0`` entries fall through to the
lifter's first-node-as-entry fallback and to
:func:`_validate_termination`, which already produce their own
diagnostics.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class EntryUniquenessCheck(PlanCheck):
    """Reject plans that declare more than one entry node."""

    check_id = "entry_uniqueness"
    label = "Exactly one entry node (typed-port D4 contract)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        """Return a :class:`PlanLiftError` if more than one node is marked entry."""
        entries = [n.id for n in plan.nodes if n.entry]
        if len(entries) > 1:
            return PlanLiftError(
                f"plan {plan_id!r}: multiple entry nodes {entries!r}; "
                f"exactly one entry is required for the typed-port kernel "
                f"to know where to start. Remove ``entry: true`` from all "
                f"but one node, or remove them all and let the lifter's "
                f"first-node-as-entry fallback pick the canonical entry.",
                plan_id=plan_id,
            )
        return None


__all__ = ["EntryUniquenessCheck"]
