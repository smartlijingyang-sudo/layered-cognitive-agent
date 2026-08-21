"""ModularBrain —— Brain 串联 Reasoner / Critic，直接构建 Decision。

ADR-0068：默认 reflect 实现为 Brain 内部 ``_default_reflect`` 私有方法
（不调 Critic Protocol）；Critic 协议保留作 custom 注入接口。

PR-4 think.guard 原子化迁移（ADR-0074）：

- ``state.active_template`` 不再由 Brain 直接写；改为通过
  ``reducer.apply_skill_route(state, active_template)`` 收口（C4 兑现）
- ``agent_gates``（think.guard 投稿，来自 ControlPlan.by_slot['think.guard']）
  顺序由 ControlEntry.order 决定；priority 高的先调
- 删除任何 ``_gate_chain`` / ``_gates_chain`` 字段（CV4：不允许 C1
  子步骤独立字段；gate 列表由 ControlPlan 投影）
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    Brain,
    Critic,
    DecisionGate,
    Reasoner,
    Reducer,
    SkillRouter,
    SupportsShortcut,
)
from lca.layer1_cognitive.brain.llm_result import build_decision_from_response


class ModularBrain(Brain):
    """Default ``Brain``: Reasoner (call_llm) → llm_result → DecisionGate → Critic.

    LobeHub ``GeneralChatAgent`` ``llm_result`` phase: native function calling
    maps to USE_TOOL / DELEGATE / RESPOND via ``build_decision_from_response``.

    PR-4: ``reducer`` 是 PR-3 / PR-4 think.guard 原子化迁移的 seam —
    所有 state mutation 经 reducer（C4 兑现，不直接写）。如未提供，使用
    ``_LocalReducer``（仅本地兼容；生产路径必须显式注入 DefaultReducer）。
    """

    def __init__(
        self,
        reasoner: Reasoner,
        critic: Critic | None = None,
        skill_router: SkillRouter | None = None,
        decision_gate: DecisionGate | None = None,
        agent_gates: DecisionGate | None = None,
        reducer: Reducer | None = None,
    ) -> None:
        self.reasoner = reasoner
        self.critic = critic
        self.skill_router = skill_router
        self._decision_gate: DecisionGate | None = decision_gate
        self._agent_gates: DecisionGate | None = agent_gates
        # PR-4: brain 不再直接写 state；reducer 是 seam（C4 兑现）
        self.reducer = reducer if reducer is not None else _LocalReducer()

    @property
    def agent_gates(self) -> DecisionGate | None:
        return self._agent_gates

    async def think(self, state: AgentState) -> Decision:
        if self._decision_gate is not None and isinstance(self._decision_gate, SupportsShortcut):
            pre = await self._decision_gate.try_shortcut(state)
            if pre is not None:
                return pre

        if self.skill_router is not None:
            # PR-4: state mutation via reducer（C4）；never direct write
            active_template = await self.skill_router.route(state)
            state = self.reducer.apply_skill_route(state, active_template)

        response = await self.reasoner.generate_thoughts(state)
        decision = build_decision_from_response(response)

        if self._decision_gate is not None:
            decision = await self._decision_gate.enforce(state, decision)
        if self._agent_gates is not None:
            decision = await self._agent_gates.enforce(state, decision)
        return decision

    async def reflect(self, state: AgentState, observation: Observation) -> Reflection:
        if self.critic is not None:
            return await self.critic.critique(state, observation)
        return self._default_reflect(state, observation)

    @staticmethod
    def _default_reflect(state: AgentState, observation: Observation) -> Reflection:
        """Default reflect: ON_TRACK, no lesson (ADR-0068 Null 默认）。

        reasoner 不依赖 reflect 的输出做后续决策；reasoning 失败或
        lesson 缺失由 upstream Gate / StopRule 捕获。这里只返回
        协议要求的最小合法 ``Reflection``。
        """
        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.ON_TRACK,
            lesson=None,
        )


class _LocalReducer(Reducer):
    """PR-4 ModularBrain 兼容 reducer：缺省实现 apply_skill_route（C4 fold）。

    生产路径必须显式注入 ``DefaultReducer``（来自 ``lca.layer2_runtime.reducer``）
    以获得完整的 apply_* seam；本类只用于 ModularBrain 在测试 / 隔离
    启动时无 reducer 的兼容场景。

    CV4 守护：本类不放任何 C1 子步骤独立字段。
    """

    def apply_step_advanced(self, state: AgentState, step: int) -> AgentState:
        return state

    def apply_perception(self, state: AgentState, manifest) -> AgentState:
        return state

    def apply_turn(self, state: AgentState, turn) -> AgentState:
        return state

    def apply_skill_route(self, state: AgentState, active_template: str | None) -> AgentState:
        # C4 fold: active_template 由 reducer 写入 state
        state.active_template = active_template
        return state

    def apply_memory(self, state, writes) -> AgentState:
        return state

    def apply_stop(self, state, stop) -> AgentState:
        return state

    def apply_error(self, state, error) -> AgentState:
        return state

    def apply_paused(self, state, snapshot_ref) -> AgentState:
        return state
