"""Compatibility exports for plan binding.

Plan binding belongs to the plan-composer implementation.  This module keeps
existing L4 imports stable while delegating to that implementation.
"""

from lca.plugins.composer.plan_binding import (
    BindPlanError,
    PlanBindingResult,
    TeamBindingResult,
    bind_plan,
    bind_team,
)

__all__ = ["BindPlanError", "PlanBindingResult", "TeamBindingResult", "bind_plan", "bind_team"]
