"""Tests for Budget Policy Plugin (C.3)."""
import pytest
from unittest.mock import MagicMock


class TestBudgetPolicy:
    """Budget check as plugin middleware."""

    @pytest.mark.asyncio
    async def test_budget_check_passes_under_limit(self):
        """State under budget -> pass through."""
        from lca.plugins.budget_policy import budget_check_middleware

        state = MagicMock()
        state.step_count = 5
        ctx = MagicMock()
        result = await budget_check_middleware(
            "before_step", state, ctx, config={"max_steps": 100},
        )
        assert result is state

    @pytest.mark.asyncio
    async def test_budget_check_raises_over_limit(self):
        """State over budget -> raises BudgetExceededError."""
        from lca.plugins.budget_policy import (
            BudgetExceededError,
            budget_check_middleware,
        )

        state = MagicMock()
        state.step_count = 101
        ctx = MagicMock()
        with pytest.raises(BudgetExceededError):
            await budget_check_middleware(
                "before_step", state, ctx, config={"max_steps": 100},
            )

    @pytest.mark.asyncio
    async def test_budget_check_at_limit_raises(self):
        """State exactly at limit -> raises BudgetExceededError."""
        from lca.plugins.budget_policy import (
            BudgetExceededError,
            budget_check_middleware,
        )

        state = MagicMock()
        state.step_count = 100
        ctx = MagicMock()
        with pytest.raises(BudgetExceededError):
            await budget_check_middleware(
                "before_step", state, ctx, config={"max_steps": 100},
            )

    def test_manifest_declares_policy_kind(self):
        """Plugin manifest has correct id, kind, and seam_key."""
        from lca.plugins.budget_policy import manifest
        from lca.contracts.harness.plugin import PluginKind

        assert manifest.id == "lca.policy.budget"
        assert manifest.kind == PluginKind.POLICY
        assert manifest.seam_key == "agent.pre_step"
        assert manifest.middleware == ("agent.before_step",)

    def test_apply_registers_middleware(self):
        """apply() registers middleware on the registry."""
        from lca.plugins.budget_policy import apply
        from lca.contracts.harness.middleware import MiddlewareRegistration

        registry = MagicMock()
        ctx = MagicMock()
        ctx.require.return_value = registry

        apply(ctx, config={"max_steps": 50})

        registry.register.assert_called_once()
        reg_arg = registry.register.call_args[0][0]
        assert isinstance(reg_arg, MiddlewareRegistration)
        assert reg_arg.seam_key == "agent.before_step"
        assert reg_arg.plugin_id == "lca.policy.budget"
