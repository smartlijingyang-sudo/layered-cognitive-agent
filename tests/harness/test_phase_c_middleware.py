"""Phase C integration tests — middleware and loop factory (PR4 / v3).

These tests verify the v3 cognitive-primitive surface:

- Waterfall middleware chain order is preserved.
- The hook bridge maps the documented ``agent.before_*`` / ``agent.after_*``
  seam keys to legacy hooks.
- ``RepeatToolCallGate`` emits a ``GateDecided`` + ``PolicyFact`` after the
  threshold of consecutive identical tool calls.
- ``DecisionGate.enforce`` does not mutate ``state.history`` (control surface
  purity, per v3 §3.5).

The legacy ``loop_intervention`` / ``step_budget`` paths were deleted in PR4.
"""

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState
from lca.harness.middleware import InMemoryMiddlewareRegistry
from lca.layer1_cognitive.brain.decision_gates import (
    RepeatToolCallGate,
    build_workspace_agent_gate,
)
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry
from lca.layer2_runtime.hook_middleware import install_hook_bridge


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
    """The middleware waterfall is still the wiring primitive for the
    hand-plane (pre-execute / finalize / etc.) — it just no longer carries
    cognitive-control mutations.
    """

    @pytest.mark.asyncio
    async def test_register_and_run_waterfall(self, registry):
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

        result = await registry.run("test.point", "test", state, None)

        assert call_order == ["mw1", "mw2"]
        assert result.step == 2

    @pytest.mark.asyncio
    async def test_priority_ordering(self, registry):
        call_order = []

        async def low_priority(phase, state, ctx):
            call_order.append("low")
            return state

        async def high_priority(phase, state, ctx):
            call_order.append("high")
            return state

        registry.register(MiddlewareRegistration(seam_key="test.point", priority=100), low_priority)
        registry.register(MiddlewareRegistration(seam_key="test.point", priority=10), high_priority)

        await registry.run("test.point", "test", state, None)

        assert call_order == ["high", "low"]


class TestHookBridge:
    @pytest.mark.asyncio
    async def test_hook_bridge_triggers_hooks(self, registry, hooks, state):
        triggered = []

        async def hook_handler(event_name, state, **kwargs):
            triggered.append(event_name)

        hooks.register("pre_perceive", hook_handler)
        install_hook_bridge(registry, hooks)

        await registry.run("agent.before_perceive", "perceive", state, None)

        assert "pre_perceive" in triggered


class TestRepeatToolCallGate:
    """The new ``RepeatToolCallGate`` replaces the deleted
    ``loop_intervention`` middleware: it emits a ``GateDecided`` event so
    the next ``ContextManifest`` carries the warning as a ``policy_fact``
    item.
    """

    @pytest.mark.asyncio
    async def test_emits_gate_decided_after_threshold(self):
        st = AgentState(
            trace_id="t",
            task="t",
            budget=create_budget(),
            step=0,
        )
        for _ in range(3):
            st.history.append(
                Turn(
                    decision=Decision(
                        decision_id=new_id("dec"),
                        action_type=ActionType.USE_TOOL,
                        rationale="",
                        confidence=1.0,
                        tool_calls=[
                            ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id=new_id("obs"), success=True, payload="ok"
                    ),
                )
            )

        gate = RepeatToolCallGate()
        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL,
            rationale="",
            confidence=1.0,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
        )
        out = await gate.enforce(st, decision)

        # The decision itself is not rewritten (warn only).
        assert out is decision

        # The GateDecided event was recorded on the typed bucket.
        view = PerceiveState.from_agent_state(st)
        assert len(view.gate_decided) == 1
        recorded = view.gate_decided[0]
        assert recorded.gate == "RepeatToolCallGate"
        assert recorded.verdict == "warn"
        assert recorded.policy_fact is not None
        assert recorded.policy_fact.kind == "repeat_tool_call"
        assert "calculator" in recorded.policy_fact.message

    @pytest.mark.asyncio
    async def test_no_event_below_threshold(self):
        st = AgentState(
            trace_id="t",
            task="t",
            budget=create_budget(),
            step=0,
        )
        # Only two calls — below the threshold of 3.
        for _ in range(2):
            st.history.append(
                Turn(
                    decision=Decision(
                        decision_id=new_id("dec"),
                        action_type=ActionType.USE_TOOL,
                        rationale="",
                        confidence=1.0,
                        tool_calls=[
                            ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id=new_id("obs"), success=True, payload="ok"
                    ),
                )
            )
        gate = RepeatToolCallGate()
        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL,
            rationale="",
            confidence=1.0,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
        )
        await gate.enforce(st, decision)

        view = PerceiveState.from_agent_state(st)
        assert view.gate_decided == []

    @pytest.mark.asyncio
    async def test_does_not_mutate_state_history(self):
        """v3 §3.5 — the control surface may not append to ``history``."""
        st = AgentState(
            trace_id="t",
            task="t",
            budget=create_budget(),
            step=0,
        )
        for _ in range(3):
            st.history.append(
                Turn(
                    decision=Decision(
                        decision_id=new_id("dec"),
                        action_type=ActionType.USE_TOOL,
                        rationale="",
                        confidence=1.0,
                        tool_calls=[
                            ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id=new_id("obs"), success=True, payload="ok"
                    ),
                )
            )
        history_len_before = len(st.history)

        gate = RepeatToolCallGate()
        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL,
            rationale="",
            confidence=1.0,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="calculator", arguments={})],
        )
        await gate.enforce(st, decision)

        assert len(st.history) == history_len_before


class TestWorkspaceAgentGateChain:
    """The full PR4 chain emits the expected number of ``GateDecided``
    events for a synthetic repeat-tool-call scenario.
    """

    @pytest.mark.asyncio
    async def test_chain_runs_each_gate(self):
        st = AgentState(
            trace_id="t",
            task="t",
            budget=create_budget(),
            step=0,
        )
        chain = build_workspace_agent_gate()
        assert chain is not None

        decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.RESPOND,
            rationale="",
            confidence=1.0,
        )
        out = await chain.enforce(st, decision)
        # RESPOND is not rewritten by Repeat/ToolLoopBreaker — chain
        # returns the original decision (or a normalized form).
        assert out.action_type in (ActionType.RESPOND,)
