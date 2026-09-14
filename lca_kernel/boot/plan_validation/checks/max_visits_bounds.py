"""Max-visits upper-bound check.

The :class:`Plan` model validator only ensures ``max_visits > 0``;
it does not set an upper bound. A typo such as
``max_visits: 99999`` would let the interpreter revisit a node
indefinitely and stall a run. Boot should fail-loud on such
run-away budgets.

Two tiers:

- ``MAX_VISITS_HARD_CAP`` (1000) — above this, the plan is almost
  certainly a typo or runaway; the lift is rejected outright.
- ``MAX_VISITS_RECOMMENDED`` (50) — above this, the plan may be
  intentional (long retry chains, exhaustive search), but the
  operator should confirm the budget matches their intent.

Both tiers fail-loud at boot; a quieter warning is no good because
the failure mode is silent run starvation.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck

MAX_VISITS_HARD_CAP = 1000
MAX_VISITS_RECOMMENDED = 50


class MaxVisitsBoundsCheck(PlanCheck):
    """Reject plans whose ``max_visits`` exceeds sane upper bounds."""

    check_id = "max_visits_bounds"
    label = "max_visits within sane bounds (no runaway budget)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        over_hard: list[tuple[str, int]] = []
        over_recommended: list[tuple[str, int]] = []
        for n in plan.nodes:
            if n.max_visits > MAX_VISITS_HARD_CAP:
                over_hard.append((n.id, n.max_visits))
            elif n.max_visits > MAX_VISITS_RECOMMENDED:
                over_recommended.append((n.id, n.max_visits))

        if over_hard:
            names_list = ", ".join(
                f"{nid} (max_visits={mv})" for nid, mv in over_hard
            )
            return PlanLiftError(
                f"plan {plan_id!r}: node max_visits exceeds hard cap "
                f"({MAX_VISITS_HARD_CAP}): {names_list}. This would let "
                f"the interpreter revisit the node indefinitely. Lower "
                f"max_visits to a reasonable value or split the cycle "
                f"into multiple nodes with termination predicates.",
                plan_id=plan_id,
            )
        if over_recommended:
            names_list = ", ".join(
                f"{nid} (max_visits={mv})" for nid, mv in over_recommended
            )
            return PlanLiftError(
                f"plan {plan_id!r}: node max_visits exceeds recommended "
                f"({MAX_VISITS_RECOMMENDED}): {names_list}. Confirm this "
                f"is intentional or lower max_visits to avoid run-away "
                f"budgets.",
                plan_id=plan_id,
            )
        return None


__all__ = ["MaxVisitsBoundsCheck"]
