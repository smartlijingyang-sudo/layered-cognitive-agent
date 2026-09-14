"""Self-loop safety check.

Reject self-loops with ``max_visits > 1``.

A self-loop ``a → a`` with ``max_visits=1`` is fine — the kernel
visits the node once and the loop terminates because the visit
budget is exhausted. With ``max_visits > 1`` the same node can
keep traversing the self-loop until the budget runs out, which
silently inflates run cost without producing new state. Some
executors genuinely need self-loops for retry semantics, so the
cap is "raise only when the budget exceeds the safe single-visit
value" — the operator can lower ``max_visits`` to silence the
check.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class SelfLoopSafeCheck(PlanCheck):
    """Reject self-loops whose ``max_visits`` would re-enter indefinitely."""

    check_id = "self_loop_safe"
    label = "Self-loop safety (no unbounded revisit)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        for node in plan.nodes:
            if node.max_visits <= 1:
                continue
            for edge in plan.edges:
                if edge.source == node.id and edge.target == node.id:
                    return PlanLiftError(
                        f"plan {plan_id!r}: node {node.id!r} has a self-loop "
                        f"with max_visits={node.max_visits}; this lets the "
                        f"interpreter revisit the node indefinitely and "
                        f"inflates run cost. Lower ``max_visits`` to 1 or "
                        f"remove the self-loop edge.",
                        plan_id=plan_id,
                        node_id=node.id,
                    )
        return None


__all__ = ["SelfLoopSafeCheck"]
