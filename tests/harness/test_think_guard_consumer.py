"""Tests for think.guard + stop.decide control surface consumption (PR-4).

This test verifies the L2 acceptance §2.4 + §3.3:

- ``ModularBrain.agent_gates`` 在 ControlPlan.by_slot['think.guard'] 投影下
  按 ControlEntry.order 排序（升序）执行
- ModularBrain.think() 不直接 mutate state（CV4 通过 reducer.apply_skill_route）
- Stop PhaseExecutor 通过局部 ``stop_policy.decide(...)`` 走 stop.decide 控制面

v2（ADR-0221 P3）：``CompiledRunPlan.control_entries`` 与
``PluginSpec.contributes`` 均已退役。控制面绑定 = resolved profile 中启用插件
的 ``provided_capability_keys``（``phase:<phase>::control.*``）。本文件在
round-0151 按 v2 事实重写，断言意图（控制绑定到阶段）保持不变。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lca.cognition.brain.pipeline.modular_brain import ModularBrain
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols import (
    DecisionGate,
    Reasoner,
    Reducer,
    SkillRouter,
)
from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier
from lca.plugins.loop.reducer.plugin import DefaultReducer

# ── Test doubles ─────────────────────────────────────────────────────


@dataclass
class _FakeReasoner(Reasoner):
    """Returns a fixed LLMResponse.

    ADR-0220 §6：``generate_thoughts`` 已删除，Reasoner 只剩
    ``render_turn``/``complete_turn`` + ``role_profile`` boot-time seam。
    """

    response_text: str = "ok"
    role_profile: RoleProfile = field(
        default_factory=lambda: RoleProfile(
            role="test-reasoner",
            goal="test",
            backstory="test",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
    )

    def render_turn(
        self, context: object, template: object, role: object, **kwargs: object
    ) -> object:
        from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender

        return ReasonerTurnRender(
            prompt=self.response_text,
            trace=None,
            section_count=0,
            manifest=None,
            activated_skill_ids=(),
            section_outputs=None,
            total_chars=None,
            variant=None,
        )

    async def complete_turn(
        self, state: AgentState, render: object, **kwargs: object
    ) -> LLMResponse:
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


def _web_standard_phase_bindings() -> dict[str, str]:
    """web-standard 下启用插件提供的 ``phase:<phase>::`` 能力键 → 插件 id。

    v2（ADR-0221 P3）：``CompiledRunPlan.control_entries`` 恒为空 tuple，
    控制面绑定只能从 resolved profile 的 ``provided_capability_keys`` 读。
    """
    from lca.harness.profile.resolve.resolve import resolve_profile

    resolved = resolve_profile("profiles/web-standard.yaml")
    bindings: dict[str, str] = {}
    for plugin in resolved.plugins:
        if plugin.disabled:
            continue
        for key in plugin.definition.provided_capability_keys:
            if isinstance(key, str) and key.startswith("phase:"):
                bindings[key] = plugin.definition.id
    return bindings


class TestDeclarativeControlProjection:
    """生产控制只从原生 PluginSpec 贡献编译为计划绑定（v2 见上）。"""

    def test_think_guard_projection_is_bound_to_the_think_phase(self) -> None:
        bindings = _web_standard_phase_bindings()
        assert bindings.get("phase:think::control.think.guard") == "control.think.guard", (
            "think.guard 控制必须由原生插件绑定到 think 阶段"
        )

    def test_stop_control_projection_is_bound_to_the_stop_phase(self) -> None:
        bindings = _web_standard_phase_bindings()
        stop_controls = {key for key in bindings if key.startswith("phase:stop::control.")}
        # v1 的 control.stop.decide / control.stop.focus 在 ADR-0221 后已无提供方；
        # stop 控制面 = observe checkpoint/wildcard 两个原生插件绑定。
        assert stop_controls == {
            "phase:stop::control.observe.checkpoint",
            "phase:stop::control.observe.wildcard",
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
    """v2（ADR-0221）：stop.decide 控制面不再是独立的 Stop PhaseExecutor
    （``lca/plugins/loop/phase/stop/standard/plugin.py`` 已随 v1 退役）；
    stop 控制由 ``phase:stop::`` 插件绑定 + convergence policy 的
    ``STOP_DECIDE`` 槽位声明承担。
    """

    def test_stop_control_surface_is_bound_in_v2(self) -> None:
        from pathlib import Path

        assert not Path("lca/plugins/loop/phase/stop/standard/plugin.py").exists(), (
            "v1 Stop PhaseExecutor 已退役，不应复活"
        )
        bindings = _web_standard_phase_bindings()
        assert {key for key in bindings if key.startswith("phase:stop::control.")} == {
            "phase:stop::control.observe.checkpoint",
            "phase:stop::control.observe.wildcard",
        }

    def test_stop_decide_slot_is_declared_by_convergence_policy(self) -> None:
        from lca.contracts.atoms.control.slot import ControlSlot
        from lca.harness.profile.resolve.resolve import resolve_profile

        resolved = resolve_profile("profiles/web-standard.yaml")
        declarants = set()
        for plugin in resolved.plugins:
            if plugin.disabled:
                continue
            contract = getattr(plugin.definition, "contract", None)
            arch = getattr(contract, "architecture", None)
            slots = tuple(getattr(arch, "control_slots", None) or ())
            if ControlSlot.STOP_DECIDE in slots:
                declarants.add(plugin.definition.id)
        assert "convergence.policy.default" in declarants, (
            "stop.decide 槽位应由 convergence policy 插件声明"
        )
