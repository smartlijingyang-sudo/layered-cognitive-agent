"""Outer ControlPlan must declare a bounded reflect→think recovery edge.

M1 (Issue #14) — outer edge SSOT:

* Recovery control lives on ``bundles/outer/phase_main.yaml``, not on
  ``declarative-recovery`` plugin edge tables.
* Missing ``admit_recovery`` edge → **compile / boot fail** (no silent
  skip).
* Unbounded recovery (no ``loop`` / non-positive max_iterations / empty
  budget) → same fail-loud path.

This check only applies to plans whose id is ``phase.main.outer`` so
inner subgraphs are not forced to restate the outer obligation.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan, PlanEdge
from lca.contracts.protocols.graph.predicate import Predicate

from .base import PlanCheck

_OUTER_PLAN_ID = "phase.main.outer"
_SOURCE = "reflect.main"
_TARGET = "think.main"
_HINT = "admit_recovery"


def _predicate_admits_recovery(pred: Predicate | None) -> bool:
    """True when *pred* (or a child) equals ``routing.next_hint == admit_recovery``."""
    if pred is None:
        return False
    if (
        pred.kind == "eq"
        and pred.port is not None
        and pred.port.name == "routing"
        and pred.port.field == "next_hint"
        and pred.value == _HINT
    ):
        return True
    return any(_predicate_admits_recovery(child) for child in pred.children)


def _is_recovery_edge(edge: PlanEdge) -> bool:
    return (
        edge.source == _SOURCE
        and edge.target == _TARGET
        and _predicate_admits_recovery(edge.when)
    )


class AdmitRecoveryEdgeCheck(PlanCheck):
    """Outer plan must carry a bounded reflect→think ``admit_recovery`` edge.

    Fail-loud: missing edge, missing loop obligation, or unbound loop
    all raise :class:`PlanLiftError` naming the required edge. Never
    soft-skips.
    """

    check_id = "admit_recovery_edge"
    label = "Outer admit_recovery edge present and bounded"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        if plan.id != _OUTER_PLAN_ID and plan_id != _OUTER_PLAN_ID:
            return None

        recovery_edges = [e for e in plan.edges if _is_recovery_edge(e)]
        if not recovery_edges:
            return PlanLiftError(
                f"plan {plan_id!r}: missing critical recovery edge "
                f"{_SOURCE!r} → {_TARGET!r} with when "
                f"routing.next_hint == {_HINT!r}. "
                f"M1 outer edge SSOT requires this edge on "
                f"bundles/outer/phase_main.yaml; missing edge = compile fail "
                f"(no silent skip).",
                plan_id=plan_id,
            )

        for edge in recovery_edges:
            loop = edge.loop
            if loop is None:
                return PlanLiftError(
                    f"plan {plan_id!r}: recovery edge {_SOURCE!r} → {_TARGET!r} "
                    f"is missing loop obligation (maxIterations + budget). "
                    f"Unbounded admit_recovery is forbidden; add "
                    f"loop.maxIterations / loop.budget matching LoopGuard=1 "
                    f"semantics.",
                    plan_id=plan_id,
                )
            if loop.max_iterations <= 0:
                return PlanLiftError(
                    f"plan {plan_id!r}: recovery edge {_SOURCE!r} → {_TARGET!r} "
                    f"loop.max_iterations must be > 0 (got {loop.max_iterations}).",
                    plan_id=plan_id,
                )
            if not str(loop.budget or "").strip():
                return PlanLiftError(
                    f"plan {plan_id!r}: recovery edge {_SOURCE!r} → {_TARGET!r} "
                    f"loop.budget must be a non-empty budget key "
                    f"(e.g. 'run.steps').",
                    plan_id=plan_id,
                )
        return None


__all__ = ["AdmitRecoveryEdgeCheck"]
