"""ModularBrain —— Brain 串联 Reasoner / Critic，直接构建 Decision。"""

from __future__ import annotations

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
        critic: Critic,
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
        return await self.critic.critique(state, observation)
