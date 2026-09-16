"""Outer ControlPlan must bound the act→think use_tool re-ask edge.

Without ``loop.maxIterations`` the re-ask is unbounded. A stale
``decision`` port (empty shortcut visit not clearing the registry)
turns that edge into an infinite empty loop — 880 think/act visits
with a single LLM call (2026-09-16). Boot fails loud when the
obligation is missing so the bound cannot be silently dropped.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan, PlanEdge
from lca.contracts.protocols.graph.predicate import Predicate

from .base import PlanCheck

_OUTER_PLAN_ID = "phase.main.outer"
_SOURCE = "act.main"
_TARGET = "think.main"
_ACTION = "use_tool"


def _predicate_is_use_tool(pred: Predicate | None) -> bool:
    """True when *pred* (or a child) equals ``decision.action_type == use_tool``."""
    if pred is None:
        return False
    if (
        pred.kind == "eq"
        and pred.port is not None
        and pred.port.name == "decision"
        and pred.port.field == "action_type"
        and pred.value == _ACTION
    ):
        return True
    return any(_predicate_is_use_tool(child) for child in pred.children)


def _is_reask_edge(edge: PlanEdge) -> bool:
    return edge.source == _SOURCE and edge.target == _TARGET and _predicate_is_use_tool(edge.when)


class UseToolReaskEdgeCheck(PlanCheck):
    """Outer plan must carry a bounded act→think use_tool re-ask edge."""

    check_id = "use_tool_reask_edge"
    label = "Outer act→think use_tool re-ask edge present and bounded"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        if plan.id != _OUTER_PLAN_ID and plan_id != _OUTER_PLAN_ID:
            return None

        reask_edges = [e for e in plan.edges if _is_reask_edge(e)]
        if not reask_edges:
            return PlanLiftError(
                f"plan {plan_id!r}: missing critical re-ask edge "
                f"{_SOURCE!r} → {_TARGET!r} with when "
                f"decision.action_type == {_ACTION!r}. "
                f"The tool follow-up path lives on this edge; missing "
                f"it silently drops tool results.",
                plan_id=plan_id,
            )

        for edge in reask_edges:
            loop = edge.loop
            if loop is None:
                return PlanLiftError(
                    f"plan {plan_id!r}: re-ask edge {_SOURCE!r} → {_TARGET!r} "
                    f"is missing loop obligation (maxIterations + budget). "
                    f"Unbounded use_tool re-ask is forbidden.",
                    plan_id=plan_id,
                )
            if loop.max_iterations <= 0:
                return PlanLiftError(
                    f"plan {plan_id!r}: re-ask edge {_SOURCE!r} → {_TARGET!r} "
                    f"loop.max_iterations must be > 0 (got {loop.max_iterations}).",
                    plan_id=plan_id,
                )
            if not str(loop.budget or "").strip():
                return PlanLiftError(
                    f"plan {plan_id!r}: re-ask edge {_SOURCE!r} → {_TARGET!r} "
                    f"loop.budget must be a non-empty budget key "
                    f"(e.g. 'run.steps').",
                    plan_id=plan_id,
                )
        return None


__all__ = ["UseToolReaskEdgeCheck"]
