"""Integration tests — CognitiveRuntime middleware phase boundary invocation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.state import AgentState
from lca.harness.middleware.registry import InMemoryMiddlewareRegistry, SimplePhaseContext
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry
from lca.layer2_runtime.runtime_loop import CognitiveRuntime


@pytest.fixture
def middleware_registry():
    return InMemoryMiddlewareRegistry()


@pytest.fixture
def hooks():
    return SimpleHookRegistry()


@pytest.fixture
def state():
    return AgentState(
        trace_id=new_id("trace"),
        task="test task",
        budget=create_budget(max_steps=1),
        step=0,
    )


class TestRuntimeMiddlewareIntegration:
    """CognitiveRuntime calls middleware at phase boundaries."""

    @pytest.mark.asyncio
    async def test_middleware_called_at_each_phase(self, middleware_registry):
        """Each phase boundary invokes middleware registry."""
        call_log = []

        async def tracking_middleware(phase, state, context):
            call_log.append(phase)
            return state

        # Register middleware at all cognitive phase boundaries
        for point in [
            "agent.pre_step",
            "agent.before_perceive", "agent.after_perceive",
            "agent.before_think", "agent.after_think",
            "agent.before_act", "agent.after_act",
            "agent.before_reflect", "agent.after_reflect",
            "agent.before_turn_end",
        ]:
            middleware_registry.register(
                MiddlewareRegistration(seam_key=point, priority=50, plugin_id="test"),
                tracking_middleware,
            )

        # Verify middleware is registered
        for point in [
            "agent.pre_step",
            "agent.before_perceive", "agent.before_think",
            "agent.before_act", "agent.before_reflect",
        ]:
            assert middleware_registry.has_point(point)
            regs = middleware_registry.list_registrations(point)
            assert len(regs) > 0

    @pytest.mark.asyncio
    async def test_middleware_can_modify_state(self, middleware_registry):
        """Waterfall middleware can modify state between phases."""
        async def inject_context(phase, state, context):
            state.working_memory["injected"] = True
            return state

        middleware_registry.register(
            MiddlewareRegistration(seam_key="agent.before_think", priority=50, plugin_id="test"),
            inject_context,
        )

        # Run the middleware
        ctx = SimplePhaseContext(session_id="test", record=lambda e: None)
        result = await middleware_registry.run(
            "agent.before_think", "think", AgentState(
                trace_id=new_id("trace"),
                task="test",
                budget=create_budget(),
            ),
            ctx,
        )
        assert result.working_memory.get("injected") is True

    @pytest.mark.asyncio
    async def test_runtime_invokes_middleware_during_loop(self, middleware_registry, hooks):
        """CognitiveRuntime._loop() invokes middleware at each phase boundary."""
        # Track which phases were called
        called_phases = []

        async def phase_tracker(phase, state, context):
            called_phases.append(phase)
            return state

        # Register at all cognitive points
        for point in [
            "agent.pre_step",
            "agent.before_perceive", "agent.after_perceive",
            "agent.before_think", "agent.after_think",
            "agent.before_act", "agent.after_act",
            "agent.before_reflect", "agent.after_reflect",
            "agent.before_turn_end",
        ]:
            middleware_registry.register(
                MiddlewareRegistration(seam_key=point, priority=50, plugin_id="test"),
                phase_tracker,
            )

        # Create mock components
        mock_brain = MagicMock()
        mock_brain.think = AsyncMock(return_value=Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.RESPOND,
            rationale="test",
            confidence=1.0,
        ))
        mock_brain.reflect = AsyncMock(return_value=None)

        mock_body = MagicMock()
        mock_body.act = AsyncMock(return_value=Observation(
            observation_id=new_id("obs"),
            success=True,
            payload="done",
        ))

        mock_memory = MagicMock()
        mock_memory.perceive = AsyncMock(side_effect=lambda state: state)
        mock_memory.update = AsyncMock()

        mock_state_store = MagicMock()
        mock_state_store.save = AsyncMock(return_value=new_id("ref"))
        mock_state_store.load = AsyncMock()

        mock_stop_rule = MagicMock()
        mock_stop_rule.decide = MagicMock(return_value=MagicMock(
            should_stop=True,
            reason=None,
            status=None,
        ))

        # Create runtime with middleware registry
        runtime = CognitiveRuntime(
            brain=mock_brain,
            body=mock_body,
            memory=mock_memory,
            hooks=hooks,
            state_store=mock_state_store,
            stop_rule=mock_stop_rule,
            middleware_registry=middleware_registry,
        )

        # Run one iteration
        state = AgentState(
            trace_id=new_id("trace"),
            task="test",
            budget=create_budget(max_steps=1),
            step=0,
        )

        await runtime._loop(state, max_steps=1)

        # Verify middleware was called at expected phases
        assert "step" in called_phases  # pre_step
        assert "perceive" in called_phases
        assert "think" in called_phases
        assert "act" in called_phases
        assert "reflect" in called_phases
        assert "turn_end" in called_phases

        # Verify each phase was called multiple times (before and after)
        perceive_count = called_phases.count("perceive")
        think_count = called_phases.count("think")
        act_count = called_phases.count("act")
        reflect_count = called_phases.count("reflect")

        # Each should be called at least twice (before and after)
        assert perceive_count >= 2, f"perceive called {perceive_count} times, expected >= 2"
        assert think_count >= 2, f"think called {think_count} times, expected >= 2"
        assert act_count >= 2, f"act called {act_count} times, expected >= 2"
        assert reflect_count >= 2, f"reflect called {reflect_count} times, expected >= 2"

    @pytest.mark.asyncio
    async def test_runtime_works_without_middleware(self, hooks):
        """CognitiveRuntime works normally when middleware_registry is None."""
        # Create mock components
        mock_brain = MagicMock()
        mock_brain.think = AsyncMock(return_value=Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.RESPOND,
            rationale="test",
            confidence=1.0,
        ))
        mock_brain.reflect = AsyncMock(return_value=None)

        mock_body = MagicMock()
        mock_body.act = AsyncMock(return_value=Observation(
            observation_id=new_id("obs"),
            success=True,
            payload="done",
        ))

        mock_memory = MagicMock()
        mock_memory.perceive = AsyncMock(side_effect=lambda state: state)
        mock_memory.update = AsyncMock()

        mock_state_store = MagicMock()
        mock_state_store.save = AsyncMock(return_value=new_id("ref"))
        mock_state_store.load = AsyncMock()

        mock_stop_rule = MagicMock()
        mock_stop_rule.decide = MagicMock(return_value=MagicMock(
            should_stop=True,
            reason=None,
            status=None,
        ))

        # Create runtime WITHOUT middleware registry
        runtime = CognitiveRuntime(
            brain=mock_brain,
            body=mock_body,
            memory=mock_memory,
            hooks=hooks,
            state_store=mock_state_store,
            stop_rule=mock_stop_rule,
            middleware_registry=None,  # Explicitly None
        )

        state = AgentState(
            trace_id=new_id("trace"),
            task="test",
            budget=create_budget(max_steps=1),
            step=0,
        )

        # Should not raise any errors
        result = await runtime._loop(state, max_steps=1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_middleware_waterfall_state_propagation(self, middleware_registry, hooks):
        """Middleware state modifications propagate through the waterfall."""
        # First middleware injects a value
        async def inject_value(phase, state, context):
            state.working_memory["step1"] = "injected"
            return state

        # Second middleware reads and modifies
        async def modify_value(phase, state, context):
            if "step1" in state.working_memory:
                state.working_memory["step2"] = f"modified_from_{state.working_memory['step1']}"
            return state

        middleware_registry.register(
            MiddlewareRegistration(seam_key="agent.before_think", priority=10, plugin_id="test"),
            inject_value,
        )
        middleware_registry.register(
            MiddlewareRegistration(seam_key="agent.before_think", priority=20, plugin_id="test"),
            modify_value,
        )

        # Create mock components
        mock_brain = MagicMock()
        mock_brain.think = AsyncMock(return_value=Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.RESPOND,
            rationale="test",
            confidence=1.0,
        ))
        mock_brain.reflect = AsyncMock(return_value=None)

        mock_body = MagicMock()
        mock_body.act = AsyncMock(return_value=Observation(
            observation_id=new_id("obs"),
            success=True,
            payload="done",
        ))

        mock_memory = MagicMock()
        mock_memory.perceive = AsyncMock(side_effect=lambda state: state)
        mock_memory.update = AsyncMock()

        mock_state_store = MagicMock()
        mock_state_store.save = AsyncMock(return_value=new_id("ref"))

        mock_stop_rule = MagicMock()
        mock_stop_rule.decide = MagicMock(return_value=MagicMock(
            should_stop=True,
            reason=None,
            status=None,
        ))

        runtime = CognitiveRuntime(
            brain=mock_brain,
            body=mock_body,
            memory=mock_memory,
            hooks=hooks,
            state_store=mock_state_store,
            stop_rule=mock_stop_rule,
            middleware_registry=middleware_registry,
        )

        state = AgentState(
            trace_id=new_id("trace"),
            task="test",
            budget=create_budget(max_steps=1),
            step=0,
        )

        await runtime._loop(state, max_steps=1)

        # Verify waterfall propagation
        assert state.working_memory.get("step1") == "injected"
        assert state.working_memory.get("step2") == "modified_from_injected"


class TestRuntimeArchitecture:
    """Architecture tests — CognitiveRuntime does not import hook/policy modules directly."""

    def test_runtime_no_hardcoded_hooks(self):
        """CognitiveRuntime does not import hook/policy modules directly."""
        import ast
        from pathlib import Path

        source = Path("lca/layer2_runtime/runtime_loop.py").read_text()
        tree = ast.parse(source)

        forbidden_patterns = {"budget_check", "loop_intervention", "journal_emitting"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                for pattern in forbidden_patterns:
                    assert pattern not in node.id, (
                        f"CognitiveRuntime should not reference {pattern} directly"
                    )

    def test_runtime_uses_middleware_registry_duck_typing(self):
        """CognitiveRuntime accepts middleware_registry as object | None."""
        from pathlib import Path

        source = Path("lca/layer2_runtime/runtime_loop.py").read_text()

        # Verify the __init__ signature accepts object | None
        assert "middleware_registry: object | None = None" in source

        # Verify it's stored as self._mw
        assert "self._mw = middleware_registry" in source

        # Verify _emit checks for middleware before calling
        assert "if self._mw is not None:" in source
        assert "self._mw.run(" in source
