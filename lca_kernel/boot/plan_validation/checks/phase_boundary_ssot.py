"""Plan-id alias-suffix check.

Reject plan ids that use resource-alias suffixes (``_payload``,
``_outcome``, ``_artifact``) — a generic anti-pattern in graph
configuration systems where a node label couples a logical
identifier to a transient resource shape.

Why this matters
----------------

A plan id that ends in ``_payload`` / ``_outcome`` / ``_artifact``
binds the identifier to a *physical* representation rather than
the logical contract. When the underlying shape drifts (data
format change, port rename, new field added), the alias silently
keeps the old reference and the value never reaches the
downstream consumer.

This is a **framework-level** check — it does not depend on any
project vocabulary (no ``phase.`` / ``concept.`` / ``lca.``
namespace mentioned). The alias suffixes are a universal
graph-design anti-pattern shared across typed-port, message-queue,
and DAG runtimes.

The fix is always the same: rename the plan id to a logical
namespace (e.g. ``<ns>.<name>``) and use the typed-port contract
to communicate values across boundaries.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class PlanIdAliasSuffixCheck(PlanCheck):
    """Plan ids must not couple logical identity to physical-resource shape.

    Rejects any plan id ending in an alias suffix (``_payload`` /
    ``_outcome`` / ``_artifact``) or mixing alias + resource
    semantics mid-id. Catching this at boot prevents the silent
    value-loss that follows when the physical shape drifts but
    the alias still binds to the old reference.
    """

    check_id = "plan_id_alias_suffix"
    label = "Plan id avoids resource-alias suffixes"

    _ALIAS_SUFFIXES = (
        "_payload",
        "_outcome",
        "_artifact",
    )

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        plan_id_lower = plan_id.lower()
        for suffix in self._ALIAS_SUFFIXES:
            if plan_id_lower.endswith(suffix):
                return PlanLiftError(
                    f"plan {plan_id!r}: id ends in resource-alias "
                    f"suffix {suffix!r}. Logical plan ids must "
                    f"reference the contract (typed port, role, "
                    f"namespace) — not the physical shape — so "
                    f"shape changes don't silently break bindings.",
                    plan_id=plan_id,
                )
        for needle in ("_payload_", "_outcome_", "_artifact_"):
            if needle in plan_id_lower:
                return PlanLiftError(
                    f"plan {plan_id!r}: id mixes resource-alias "
                    f"with logical semantics (mid-id {needle!r}); "
                    f"rename to a clean logical id so the alias "
                    f"doesn't shadow downstream lookups.",
                    plan_id=plan_id,
                )
        return None


__all__ = ["PlanIdAliasSuffixCheck"]
