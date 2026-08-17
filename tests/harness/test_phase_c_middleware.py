"""Phase C integration tests — middleware and loop factory."""

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state import AgentState
from lca.harness.middleware import InMemoryMiddlewareRegistry
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry
from lca.layer2_runtime.hook_middleware import install_hook_bridge
from lca.layer2_runtime.loop_intervention_mw import (
    install_loop_intervention,
)


@pytest.fixture
def registry():
    return InMemoryMiddlewareRegistry()


@pytest.fixture
def hooks():
    return SimpleHookRegistry()


@pytest.fixture
def state():
    return AgentState(
        trace_id="test",
        task="test task",
        budget=create_budget(),
        step=0,
    )


class TestMiddlewareRegistry:
    def test_register_and_run_waterfall(self, registry):
        """Waterfall middleware should chain and pass modified state."""
        call_order = []

        async def mw1(phase, state, ctx):
            call_order.append("mw1")
            state.step = 1
            return state

        async def mw2(phase, state, ctx):
            call_order.append("mw2")
            state.step = state.step + 1
            return state

        registry.register(MiddlewareRegistration(seam_key="test.point", priority=10), mw1)
        registry.register(MiddlewareRegistration(seam_key="test.point", priority=20), mw2)

        import asyncio
        result = asyncio.run(registry.run("test.point", "test", state, None))

        assert call_order == ["mw1", "mw2"]
        assert result.step == 2

    def test_register_and_run_serial(self, registry):
        """Serial middleware should run all with same state, not chain."""
        call_order = []

        async def mw1(phase, state, ctx):
            call_order.append("mw1")
            state.step = 1
            return state

        async def mw2(phase, state, ctx):
            call_order.append("mw2")
            state.step = state.step + 1
            return state

        # Register on a serial point (before_turn_end is serial by default)
        registry.register(MiddlewareRegistration(seam_key="agent.before_turn_end", priority=10), mw1)
        registry.register(MiddlewareRegistration(seam_key="agent.before_turn_end", priority=20), mw2)

        import asyncio
        result = asyncio.run(registry.run("agent.before_turn_end", "turn_end", state, None))

        assert call_order == ["mw1", "mw2"]
        # Serial mode runs all middleware on the same state object
        # mw1 sets step=1, mw2 sees step=1 and sets step=2
        assert result.step == 2

    def test_priority_ordering(self, registry):
        """Middleware should execute in priority order (lower first)."""
        call_order = []

        async def low_priority(phase, state, ctx):
            call_order.append("low")
            return state

        async def high_priority(phase, state, ctx):
            call_order.append("high")
            return state

        registry.register(MiddlewareRegistration(seam_key="test.point", priority=100), low_priority)
        registry.register(MiddlewareRegistration(seam_key="test.point", priority=10), high_priority)

        import asyncio
        asyncio.run(registry.run("test.point", "test", state, None))

        assert call_order == ["high", "low"]


class TestHookBridge:
    def test_hook_bridge_triggers_hooks(self, registry, hooks, state):
        """Hook bridge should map middleware phases to legacy hooks."""
        triggered = []

        async def hook_handler(event_name, state, **kwargs):
            triggered.append(event_name)

        hooks.register("pre_perceive", hook_handler)
        install_hook_bridge(registry, hooks)

        import asyncio
        asyncio.run(registry.run("agent.before_perceive", "perceive", state, None))

        assert "pre_perceive" in triggered

    def test_hook_bridge_passes_kwargs(self, registry, hooks, state):
        """Hook bridge should pass decision/observation/reflection from state.extra."""
        received_kwargs = {}

        async def hook_handler(event_name, state, **kwargs):
            received_kwargs.update(kwargs)

        hooks.register("post_think", hook_handler)
        install_hook_bridge(registry, hooks)

        decision = Decision(
            decision_id="d1",
            action_type=ActionType.RESPOND,
            rationale="test",
            confidence=1.0,
        )
        state.extra["_middleware_bag"] = {"decision": decision}

        import asyncio
        asyncio.run(registry.run("agent.after_think", "think", state, None))

        assert "decision" in received_kwargs
        assert received_kwargs["decision"] is decision


class TestLoopIntervention:
    def test_loop_intervention_injects_warning(self, registry, state):
        """Loop intervention should detect repeated tool calls and inject warning."""
        install_loop_intervention(registry)

        # Simulate 3 consecutive USE_TOOL decisions with Turn objects
        for i in range(3):
            decision = Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.USE_TOOL,
                rationale="test",
                confidence=1.0,
                tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
            )
            observation = Observation(
                observation_id=new_id("obs"),
                success=True,
                payload="result",
            )
            state.history.append(Turn(decision=decision, observation=observation))
            state.step += 1

        # Add decision and observation to middleware bag
        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL,
            rationale="test",
            confidence=1.0,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
        )
        observation = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload="error",
        )
        state.extra["_middleware_bag"] = {
            "decision": decision,
            "observation": observation,
        }

        import asyncio
        asyncio.run(registry.run("agent.after_act", "act", state, None))

        assert "loop_warning" in state.working_memory
        assert "calculator" in state.working_memory["loop_warning"]

    def test_loop_intervention_no_warning_below_threshold(self, registry, state):
        """Loop intervention should not warn below threshold."""
        install_loop_intervention(registry)

        # Only 2 consecutive calls (below threshold of 3)
        for i in range(2):
            decision = Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.USE_TOOL,
                rationale="test",
                confidence=1.0,
                tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
            )
            observation = Observation(
                observation_id=new_id("obs"),
                success=True,
                payload="result",
            )
            state.history.append(Turn(decision=decision, observation=observation))
            state.step += 1

        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL,
            rationale="test",
            confidence=1.0,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
        )
        observation = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload="result",
        )
        state.extra["_middleware_bag"] = {
            "decision": decision,
            "observation": observation,
        }

        import asyncio
        asyncio.run(registry.run("agent.after_act", "act", state, None))

        assert "loop_warning" not in state.working_memory
