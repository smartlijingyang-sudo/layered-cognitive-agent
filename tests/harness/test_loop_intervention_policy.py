"""Tests for Loop Intervention Policy Plugin (C.3)."""
import pytest
from unittest.mock import MagicMock


class TestLoopInterventionPolicy:
    """Detect consecutive identical tool calls and intervene."""

    @pytest.mark.asyncio
    async def test_no_intervention_on_different_tools(self):
        """Different tool calls -> no intervention."""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware

        state = {"recent_tools": ["read", "write", "exec"]}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert result == state

    @pytest.mark.asyncio
    async def test_intervention_on_consecutive_identical(self):
        """N consecutive identical tool calls -> intervention flag."""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware

        state = {"recent_tools": ["read", "read", "read"]}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert result.get("loop_intervention") is True

    @pytest.mark.asyncio
    async def test_no_intervention_below_threshold(self):
        """Fewer than threshold calls -> no intervention."""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware

        state = {"recent_tools": ["read", "read"]}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert result == state
        assert result.get("loop_intervention") is None

    @pytest.mark.asyncio
    async def test_intervention_with_custom_threshold(self):
        """Custom threshold of 5 -> intervention after 5 identical calls."""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware

        state = {"recent_tools": ["write", "write", "write", "write", "write"]}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 5},
        )
        assert result.get("loop_intervention") is True

    @pytest.mark.asyncio
    async def test_no_intervention_empty_recent_tools(self):
        """Empty recent_tools -> no intervention."""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware

        state = {"recent_tools": []}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert result == state

    @pytest.mark.asyncio
    async def test_does_not_mutate_original_state(self):
        """Middleware returns new dict, not mutated original."""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware

        state = {"recent_tools": ["read", "read", "read"]}
        original_id = id(state)
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert id(result) != original_id
        assert "loop_intervention" not in state  # original unchanged

    def test_manifest_declares_policy_kind(self):
        """Plugin manifest has correct id, kind, and seam_key."""
        from lca.plugins.loop_intervention_policy import manifest
        from lca.contracts.harness.plugin import PluginKind

        assert manifest.id == "lca.policy.loop_intervention"
        assert manifest.kind == PluginKind.POLICY
        assert manifest.seam_key == "agent.after_act"
        assert manifest.middleware == ("agent.after_act",)

    def test_apply_registers_middleware(self):
        """apply() registers middleware on the registry."""
        from lca.plugins.loop_intervention_policy import apply
        from lca.contracts.harness.middleware import MiddlewareRegistration

        registry = MagicMock()
        ctx = MagicMock()
        ctx.require.return_value = registry

        apply(ctx, config={"threshold": 3})

        registry.register.assert_called_once()
        reg_arg = registry.register.call_args[0][0]
        assert isinstance(reg_arg, MiddlewareRegistration)
        assert reg_arg.seam_key == "agent.after_act"
        assert reg_arg.plugin_id == "lca.policy.loop_intervention"
        assert reg_arg.priority == 20
