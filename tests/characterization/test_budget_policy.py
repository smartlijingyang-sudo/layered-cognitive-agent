"""BudgetPolicy strategy tests — strict and non-strict mode validation."""

from __future__ import annotations

import importlib
import os
from unittest.mock import MagicMock

from lca.contracts.budget import BudgetPolicyViolation
from lca.contracts.protocols import BudgetAware, BudgetPolicy
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.layer4_app.policies import SupervisorBudgetPolicy


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


class TestSupervisorBudgetPolicyIsProtocol:
    def test_satisfies_budget_policy_protocol(self) -> None:
        policy = SupervisorBudgetPolicy()
        assert isinstance(policy, BudgetPolicy)


class TestNonStrictMode:
    """Default mode logs but does not raise."""

    def test_low_steps_does_not_raise(self) -> None:
        os.environ.pop("BUDGET_POLICY_STRICT_MODE", None)
        importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))
        policy = SupervisorBudgetPolicy()
        policy.validate(_make_aware(max_steps=5))

    def test_none_wall_clock_does_not_raise(self) -> None:
        os.environ.pop("BUDGET_POLICY_STRICT_MODE", None)
        importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))
        policy = SupervisorBudgetPolicy()
        policy.validate(_make_aware(max_wall_clock_seconds=None))

    def test_adequate_budget_passes_silently(self) -> None:
        os.environ.pop("BUDGET_POLICY_STRICT_MODE", None)
        importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))
        policy = SupervisorBudgetPolicy()
        policy.validate(_make_aware(max_steps=30, max_wall_clock_seconds=600))


class TestStrictMode:
    """BUDGET_POLICY_STRICT_MODE=1 raises BudgetPolicyViolation."""

    def test_low_steps_raises(self) -> None:
        os.environ["BUDGET_POLICY_STRICT_MODE"] = "1"
        importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))
        from lca.layer4_app.policies import SupervisorBudgetPolicy

        policy = SupervisorBudgetPolicy()
        try:
            import pytest

            with pytest.raises(BudgetPolicyViolation) as exc_info:
                policy.validate(_make_aware(max_steps=5))
            assert exc_info.value.field == "max_steps"
            assert exc_info.value.minimum == 20
            assert exc_info.value.actual == 5
        finally:
            os.environ.pop("BUDGET_POLICY_STRICT_MODE", None)
            importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))

    def test_none_wall_clock_raises(self) -> None:
        os.environ["BUDGET_POLICY_STRICT_MODE"] = "1"
        importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))
        from lca.layer4_app.policies import SupervisorBudgetPolicy

        policy = SupervisorBudgetPolicy()
        try:
            import pytest

            with pytest.raises(BudgetPolicyViolation) as exc_info:
                policy.validate(_make_aware(max_steps=30, max_wall_clock_seconds=None))
            assert exc_info.value.field == "max_wall_clock_seconds"
        finally:
            os.environ.pop("BUDGET_POLICY_STRICT_MODE", None)
            importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))

    def test_low_wall_clock_raises(self) -> None:
        os.environ["BUDGET_POLICY_STRICT_MODE"] = "1"
        importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))
        from lca.layer4_app.policies import SupervisorBudgetPolicy

        policy = SupervisorBudgetPolicy()
        try:
            import pytest

            with pytest.raises(BudgetPolicyViolation) as exc_info:
                policy.validate(_make_aware(max_steps=30, max_wall_clock_seconds=10))
            assert exc_info.value.field == "max_wall_clock_seconds"
            assert exc_info.value.minimum == 300
            assert exc_info.value.actual == 10
        finally:
            os.environ.pop("BUDGET_POLICY_STRICT_MODE", None)
            importlib.reload(__import__("lca.layer4_app.policies", fromlist=["policies"]))


class TestBudgetPolicyViolationFields:
    def test_carries_structured_fields(self) -> None:
        err = BudgetPolicyViolation("supervisor", "max_steps", 20, 5)
        assert err.agent_role == "supervisor"
        assert err.field == "max_steps"
        assert err.minimum == 20
        assert err.actual == 5
        assert "max_steps" in str(err)
        assert "20" in str(err)
        assert "5" in str(err)
