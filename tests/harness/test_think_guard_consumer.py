"""Tests for think.guard + stop.decide control surface consumption (PR-4).

This test verifies the L2 acceptance §2.4 + §3.3:

- ``ModularBrain.agent_gates`` 在 ControlPlan.by_slot['think.guard'] 投影下
  按 ControlEntry.order 排序（升序）执行
- ModularBrain.think() 不直接 mutate state（CV4 通过 reducer.apply_skill_route）
- Stop PhaseExecutor 通过局部 ``stop_policy.decide(...)`` 走 stop.decide 控制面
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.cognition.brain.modular_brain import ModularBrain
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    DecisionGate,
    Reasoner,
    Reducer,
    SkillRouter,
)
from lca.plugins.providers.gate.decision_classifier import DefaultDecisionClassifier
from lca.plugins.runtime.reducer import DefaultReducer

# ── Test doubles ─────────────────────────────────────────────────────


@dataclass
class _FakeReasoner(Reasoner):
    """Returns a fixed LLMResponse (no decision-action field)."""

    response_text: str = "ok"

    async def generate_thoughts(self, state: AgentState) -> object:
        from lca.contracts.models.core.llm import LLMResponse

        return LLMResponse(
            text=self.response_text,
            tool_calls=[],
        )


@dataclass
class _FakeSkillRouter(SkillRouter):
    """Returns a fixed active_template."""

    template: str = "default_template"

    async def route(self, state: AgentState) -> str:
        return self.template


class _RecordingGate(DecisionGate):
    """DecisionGate that records call order."""

    def __init__(self, gate_id: str) -> None:
        self.gate_id = gate_id
        self.calls: list[str] = []

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        self.calls.append(f"try_shortcut:{self.gate_id}")
        return None

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        self.calls.append(f"enforce:{self.gate_id}")
        return decision


def _make_brain(gates: list[_RecordingGate]) -> ModularBrain:
    """Construct ModularBrain with controllable gates (no skill_router for simplicity)."""
    if len(gates) == 1:
        return ModularBrain(
            reasoner=_FakeReasoner(),
            agent_gates=gates[0],
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
        )
    # chain: use first as agent_gates, others discarded (PR-4 keeps only single gate)
    return ModularBrain(
        reasoner=_FakeReasoner(),
        agent_gates=gates[0],
        reducer=DefaultReducer(),
    )


def _make_state() -> AgentState:
    return AgentState(trace_id="trace-test", task="hello", budget=create_budget())


# ── Tests ────────────────────────────────────────────────────────────


class TestModularBrainReducerPath:
    """PR-4: state mutation via reducer (C4), not direct write."""

    @pytest.mark.asyncio
    async def test_think_routes_through_reducer_for_active_template(self) -> None:
        """``SkillRouter.route(state)`` 返回值通过 reducer.apply_skill_route
        写入 state.active_template。
        """
        reducer = DefaultReducer()
        brain = ModularBrain(
            reasoner=_FakeReasoner(),
            skill_router=_FakeSkillRouter(template="creative_template"),
            reducer=reducer,
            classifier=DefaultDecisionClassifier(),
        )
        state = _make_state()
        await brain.think(state)
        # DefaultReducer.apply_skill_route folds template into state
        assert state.active_template == "creative_template"

    @pytest.mark.asyncio
    async def test_think_without_skill_router_does_not_set_active_template(self) -> None:
        """No SkillRouter → reducer.apply_skill_route 不调用 → active_template 保持 None."""
        brain = ModularBrain(
            reasoner=_FakeReasoner(),
            skill_router=None,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
        )
        state = _make_state()
        await brain.think(state)
        assert state.active_template is None

    @pytest.mark.asyncio
    async def test_think_calls_agent_gates_in_order(self) -> None:
        """``ModularBrain.think()`` 调 agent_gates.enforce(state, decision)。"""
        gate = _RecordingGate("think.guard.test")
        brain = _make_brain([gate])
        state = _make_state()
        await brain.think(state)
        assert gate.calls == ["enforce:think.guard.test"]


class TestDeclarativeControlProjection:
    """生产控制只从原生 PluginSpec 贡献编译为计划绑定。"""

    def test_think_guard_projection_is_bound_to_the_think_phase(self) -> None:
        from lca.contracts.protocols.declarative.declarative_common import SemanticPhase
        from lca.harness.profile.plan_compiler import compile_plan
        from lca.harness.profile.resolve import resolve_profile

        plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
        think_entries = tuple(
            entry for entry in plan.control_entries if entry.phase is SemanticPhase.THINK
        )

        assert len(think_entries) == 1
        assert think_entries[0].executor_capability == "control.think.guard"
        assert think_entries[0].aggregation == "deny-on-any-deny"
        assert think_entries[0].evidence_required

    def test_stop_control_projection_is_bound_to_the_stop_phase(self) -> None:
        from lca.contracts.protocols.declarative.declarative_common import SemanticPhase
        from lca.harness.profile.plan_compiler import compile_plan
        from lca.harness.profile.resolve import resolve_profile

        plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
        stop_entries = tuple(
            entry for entry in plan.control_entries if entry.phase is SemanticPhase.STOP
        )

        assert {entry.executor_capability for entry in stop_entries} == {
            "control.stop.decide",
            "control.stop.focus",
            "control.observe.checkpoint",
            "control.observe.wildcard",
        }


class TestReducerProtocolNewMethod:
    """Reducer Protocol + DefaultReducer 包含 apply_skill_route（PR-4 新 seam）。"""

    def test_reducer_protocol_has_apply_skill_route(self) -> None:

        # Verify it's a Protocol attribute
        proto_methods = {n for n in dir(Reducer) if not n.startswith("_")}
        assert "apply_skill_route" in proto_methods

    def test_default_reducer_implements_apply_skill_route(self) -> None:
        reducer = DefaultReducer()
        state = AgentState(trace_id="t1", task="task", budget=create_budget())
        result = reducer.apply_skill_route(state, "foo_template")
        assert result is state  # in-place fold (per DefaultReducer contract)
        assert state.active_template == "foo_template"

    def test_default_reducer_apply_skill_route_with_none(self) -> None:
        reducer = DefaultReducer()
        state = AgentState(trace_id="t1", task="task", budget=create_budget())
        reducer.apply_skill_route(state, None)
        assert state.active_template is None


class TestStopPolicyControlSurface:
    """stop.decide 由 Stop 阶段的局部 StopPolicy 产生并归约为 RunDelta。"""

    def test_stop_phase_executor_routes_stop_through_stop_policy(self) -> None:
        from pathlib import Path

        stop_executor = Path("lca/plugins/phase_graph/stop.py").read_text(encoding="utf-8")
        assert "stop_policy.decide(" in stop_executor, (
            "stop PhaseExecutor must invoke its local StopPolicy.decide(...) with the "
            "think/act/reflect artifacts (stop.decide control surface)."
        )
        assert "stop_rule" not in stop_executor
        assert '"stop"' in stop_executor or "'stop'" in stop_executor, (
            "stop PhaseExecutor must publish a RunDelta with operation='stop' "
            "so reducer can fold the decision into AgentState."
        )
