"""BudgetPolicy strategy tests — resolve returns corrected budget limits.

BudgetPolicy.resolve now takes primitive data (*, max_steps, max_wall_clock_seconds, role)
instead of a BudgetAware agent. BudgetAware was removed (2026-08-30 cleanup).
"""

from __future__ import annotations

from lca.application.policies import LeadBudgetPolicy
from lca.contracts.models.core.budget import (
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    LEAD_MIN_MAX_STEPS,
    BudgetLimits,
)
from lca.contracts.protocols import BudgetPolicy


class TestLeadBudgetPolicyIsProtocol:
    def test_satisfies_budget_policy_protocol(self) -> None:
        policy = LeadBudgetPolicy()
        assert isinstance(policy, BudgetPolicy)


class TestResolveReturnsBudgetLimits:
    def test_returns_budget_limits_instance(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(max_steps=30, max_wall_clock_seconds=600, role="supervisor")
        assert isinstance(result, BudgetLimits)

    def test_below_floor_bumped(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(max_steps=5, max_wall_clock_seconds=10, role="supervisor")
        assert result.max_steps == LEAD_MIN_MAX_STEPS
        assert result.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_at_floor_unchanged(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(
            max_steps=LEAD_MIN_MAX_STEPS,
            max_wall_clock_seconds=DEFAULT_MAX_WALL_CLOCK_SECONDS,
            role="supervisor",
        )
        assert result.max_steps == LEAD_MIN_MAX_STEPS
        assert result.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_above_floor_unchanged(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(max_steps=50, max_wall_clock_seconds=600, role="supervisor")
        assert result.max_steps == 50
        assert result.max_wall_clock_seconds == 600

    def test_none_wall_clock_set_to_default(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(max_steps=50, max_wall_clock_seconds=None, role="supervisor")
        assert result.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_role_passed_through(self) -> None:
        """Role is part of the contract; verify it doesn't blow up when varied."""
        policy = LeadBudgetPolicy()
        for role in ("lead", "member", "supervisor", "worker"):
            result = policy.resolve(
                max_steps=LEAD_MIN_MAX_STEPS,
                max_wall_clock_seconds=DEFAULT_MAX_WALL_CLOCK_SECONDS,
                role=role,
            )
            assert result.max_steps == LEAD_MIN_MAX_STEPS
