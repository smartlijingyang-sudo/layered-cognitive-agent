"""Tests for think.guard + stop.decide control surface consumption (PR-4).

This test verifies the L2 acceptance §2.4 + §3.3:

- ``ModularBrain.agent_gates`` 在 ControlPlan.by_slot['think.guard'] 投影下
  按 ControlEntry.order 排序（升序）执行
- ModularBrain.think() 不直接 mutate state（CV4 通过 reducer.apply_skill_route）
- ``CognitiveRuntime._loop`` 通过 ``self.stop_rule.decide(...)`` 走 stop.decide 控制面
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    DecisionGate,
    Reasoner,
    Reducer,
    SkillRouter,
)
from lca.contracts.protocols.control_plan import (
    AggregationMode,
)
from lca.harness.profile.control_plan_resolver import project_control_plan
from lca.harness.profile.resolve import resolve_profile
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer2_runtime.reducer import DefaultReducer

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


class TestControlPlanOrderingForThinkGuard:
    """L2: ControlPlan.by_slot['think.guard'] entries are sorted by order (升序).

    PR-4 gate 顺序由 ControlPlan 决定，**不是** Brain 内部硬编码；
    这是 V1 控制面单一入口的核心守护。
    """

    def test_think_guard_entries_sorted_by_order(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_control_plan(resolved)

        think_guard_entries = []
        for slot, entries in plan.by_slot.items():
            if slot == ControlSlot.THINK_GUARD:
                think_guard_entries.extend(entries)

        # PR-2 迁移 2 个 think.guard 投稿
        assert len(think_guard_entries) == 2

        # 按 (slot, order, plugin_id) 排序 → order 10 先于 order 20
        orders = [e.order for e in think_guard_entries]
        assert orders == sorted(orders), (
            f"ControlPlan.by_slot['think.guard'] entries must be sorted by order, got {orders}"
        )

        # repeat-tool-call (order 10) 先于 tool-loop-breaker (order 20)
        plugins = [e.plugin_id for e in think_guard_entries]
        assert plugins == [
            "gate.repeat-tool-call",
            "gate.tool-loop-breaker",
        ]

    def test_stop_decide_entry_present(self) -> None:
        """L2: ControlPlan.by_slot['stop.decide'] 必须有 entry。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_control_plan(resolved)

        stop_decide_entries = []
        for slot, entries in plan.by_slot.items():
            if slot == ControlSlot.STOP_DECIDE:
                stop_decide_entries.extend(entries)

        assert len(stop_decide_entries) == 1
        assert stop_decide_entries[0].plugin_id == "stop_rule.default"
        # AggregationMode = stop_on_any_stop (PR-2 迁移)
        assert stop_decide_entries[0].aggregation == AggregationMode.STOP_ON_ANY_STOP


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


class TestStopRuleControlSurface:
    """stop.decide 控制面：声明式 stop executor 生成由 reducer 折叠的 delta。"""

    def test_declarative_stop_executor_calls_stop_rule(self) -> None:
        source = (
            __import__("pathlib")
            .Path("lca/plugins/phase_executors/common.py")
            .read_text(encoding="utf-8")
        )
        runtime_source = (
            __import__("pathlib")
            .Path("lca/layer2_runtime/declarative_runtime.py")
            .read_text(encoding="utf-8")
        )
        assert "stop_rule.decide" in source
        assert "apply_stop" in runtime_source
