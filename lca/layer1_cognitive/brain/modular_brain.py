"""ModularBrain —— Brain 串联 Reasoner / Critic，直接构建 Decision。

ADR-0068：默认 reflect 实现为 Brain 内部 ``_default_reflect`` 私有方法
（不调 Critic Protocol）；Critic 协议保留作 custom 注入接口。
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
    SkillRouter,
    SupportsShortcut,
)
from lca.layer1_cognitive.brain.llm_result import build_decision_from_response


class ModularBrain(Brain):
    """Default ``Brain``: Reasoner (call_llm) → llm_result → DecisionGate → Critic.

    LobeHub ``GeneralChatAgent`` ``llm_result`` phase: native function calling
    maps to USE_TOOL / DELEGATE / RESPOND via ``build_decision_from_response``.
    """

    def __init__(
        self,
        reasoner: Reasoner,
        critic: Critic | None = None,
        skill_router: SkillRouter | None = None,
        decision_gate: DecisionGate | None = None,
        agent_gates: DecisionGate | None = None,
    ) -> None:
        self.reasoner = reasoner
        self.critic = critic
        self.skill_router = skill_router
        self._decision_gate: DecisionGate | None = decision_gate
        self._agent_gates: DecisionGate | None = agent_gates

    @property
    def agent_gates(self) -> DecisionGate | None:
        return self._agent_gates

    async def think(self, state: AgentState) -> Decision:
        if self._decision_gate is not None and isinstance(self._decision_gate, SupportsShortcut):
            pre = await self._decision_gate.try_shortcut(state)
            if pre is not None:
                return pre

        if self.skill_router is not None:
            state.active_template = await self.skill_router.route(state)

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
        """Default reflect: ON_TRACK, no lesson (ADR-0068 Null 默认)。

        reasoner 不依赖 reflect 的输出做后续决策；reasoning 失败或
        lesson 缺失由 upstream Gate / StopRule 捕获。这里只返回
        协议要求的最小合法 ``Reflection``。
        """
        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.ON_TRACK,
            lesson=None,
        )
