"""Budget policy implementations — composition-time validation strategies.

Each policy validates an agent's budget fields against minimums
appropriate for its role. Policies are registered in the component
registry under ComponentKind.BUDGET_POLICY and resolved by name
(e.g. "supervisor").
"""

from __future__ import annotations

import os

import structlog

from lca.contracts.budget import (
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    SUPERVISOR_MIN_MAX_STEPS,
    BudgetPolicyViolation,
)
from lca.contracts.protocols import BudgetAware

_log = structlog.get_logger("lca.assembly.budget")

_STRICT_MODE = os.environ.get("BUDGET_POLICY_STRICT_MODE", "0") in ("1", "true", "yes")


class SupervisorBudgetPolicy:
    """Validate supervisor budget floors.

    Strict mode (BUDGET_POLICY_STRICT_MODE=1): raises
    BudgetPolicyViolation when max_steps or max_wall_clock_seconds
    are below required minimums.

    Non-strict mode (default): logs a structured warning when
    promotion occurs, allowing observation of which callers need
    fixing before the switch to strict mode.
    """

    def validate(self, agent: BudgetAware) -> None:
        role = agent.role_profile.role
        if agent.max_steps < SUPERVISOR_MIN_MAX_STEPS:
            if _STRICT_MODE:
                raise BudgetPolicyViolation(
                    role, "max_steps", SUPERVISOR_MIN_MAX_STEPS, agent.max_steps
                )
            _log.warning(
                "budget_promoted",
                agent=role,
                field="max_steps",
                actual=agent.max_steps,
                minimum=SUPERVISOR_MIN_MAX_STEPS,
                strict_mode=False,
            )
        if agent.max_wall_clock_seconds is None:
            if _STRICT_MODE:
                raise BudgetPolicyViolation(
                    role, "max_wall_clock_seconds", DEFAULT_MAX_WALL_CLOCK_SECONDS, 0
                )
            _log.warning(
                "budget_promoted",
                agent=role,
                field="max_wall_clock_seconds",
                actual=None,
                minimum=DEFAULT_MAX_WALL_CLOCK_SECONDS,
                strict_mode=False,
            )
        elif agent.max_wall_clock_seconds < DEFAULT_MAX_WALL_CLOCK_SECONDS:
            if _STRICT_MODE:
                raise BudgetPolicyViolation(
                    role,
                    "max_wall_clock_seconds",
                    DEFAULT_MAX_WALL_CLOCK_SECONDS,
                    agent.max_wall_clock_seconds,
                )
            _log.warning(
                "budget_promoted",
                agent=role,
                field="max_wall_clock_seconds",
                actual=agent.max_wall_clock_seconds,
                minimum=DEFAULT_MAX_WALL_CLOCK_SECONDS,
                strict_mode=False,
            )
