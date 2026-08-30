"""BudgetPolicy strategy tests — resolve returns corrected budget limits."""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.contracts.models.core.budget import (
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    LEAD_MIN_MAX_STEPS,
    BudgetLimits,
)
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols import BudgetAware, BudgetPolicy
from lca.application.policies import LeadBudgetPolicy


def _make_aware(
    max_steps: int = 5,
    max_wall_clock_seconds: int | None = 10,
    role: str = "supervisor",
) -> BudgetAware:
    rp = RoleProfile(
        role=role,
        goal="test",
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    obj = MagicMock()
    obj.max_steps = max_steps
    obj.max_wall_clock_seconds = max_wall_clock_seconds
    obj.role_profile = rp
    return obj


class TestLeadBudgetPolicyIsProtocol:
    def test_satisfies_budget_policy_protocol(self) -> None:
        policy = LeadBudgetPolicy()
        assert isinstance(policy, BudgetPolicy)


class TestResolveReturnsBudgetLimits:
    def test_returns_budget_limits_instance(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(_make_aware(max_steps=30, max_wall_clock_seconds=600))
        assert isinstance(result, BudgetLimits)

    def test_below_floor_bumped(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(_make_aware(max_steps=5, max_wall_clock_seconds=10))
        assert result.max_steps == LEAD_MIN_MAX_STEPS
        assert result.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_at_floor_unchanged(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(
            _make_aware(
                max_steps=LEAD_MIN_MAX_STEPS,
                max_wall_clock_seconds=DEFAULT_MAX_WALL_CLOCK_SECONDS,
            )
        )
        assert result.max_steps == LEAD_MIN_MAX_STEPS
        assert result.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_above_floor_unchanged(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(_make_aware(max_steps=50, max_wall_clock_seconds=600))
        assert result.max_steps == 50
        assert result.max_wall_clock_seconds == 600

    def test_none_wall_clock_set_to_default(self) -> None:
        policy = LeadBudgetPolicy()
        result = policy.resolve(_make_aware(max_wall_clock_seconds=None))
        assert result.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS
