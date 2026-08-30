"""默认的认知子流程实现。

本模块承载标准 Think / Reflect 编排，而非 ``ModularBrain``。生产组合通过
provider plugin 显式选择这些实现；因此，替换某一认知子流程不再需要复制或修改
Brain 门面、阶段执行器或 Agent Loop。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    Critic,
    DecisionGate,
    Reasoner,
    SkillRouter,
    SupportsShortcut,
)
from lca.contracts.protocols.think.cognitive_pipeline import (
    CognitiveReflectionPipeline,
    CognitiveThinkPipeline,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.contracts.protocols.state.reducer import Reducer


class StandardCognitiveThinkPipeline(CognitiveThinkPipeline):
    """Preserve the standard ordered Think primitive composition.

    The order is intentionally explicit and externally replaceable: shortcut,
    skill route, reasoner, classifier, local gate, then plan-bound agent gates.
    ``Reducer.apply_skill_route`` remains the only state-projection operation in
    this flow.
    """

    async def decide(
        self,
        *,
        state: AgentState,
        reasoner: Reasoner,
        classifier: DecisionClassifier,
        skill_router: SkillRouter | None,
        decision_gate: DecisionGate | None,
        agent_gates: DecisionGate | None,
        reducer: Reducer | None,
    ) -> Decision:
        if decision_gate is not None and isinstance(decision_gate, SupportsShortcut):
            shortcut = await decision_gate.try_shortcut(state)
            if shortcut is not None:
                return shortcut

        routed_state = state
        if skill_router is not None:
            if reducer is None:
                raise RuntimeError(
                    "CognitiveThinkPipeline requires Reducer when SkillRouter is configured"
                )
            active_template = await skill_router.route(state)
            routed_state = reducer.apply_skill_route(state, active_template)

        response = await reasoner.generate_thoughts(routed_state)
        decision = classifier.classify(response)
        if decision_gate is not None:
            decision = await decision_gate.enforce(routed_state, decision)
        if agent_gates is not None:
            decision = await agent_gates.enforce(routed_state, decision)
        return decision


class StandardCognitiveReflectionPipeline(CognitiveReflectionPipeline):
    """Use the configured critic or return the explicit Null reflection."""

    async def reflect(
        self,
        *,
        state: AgentState,
        observation: Observation,
        critic: Critic | None,
    ) -> Reflection:
        if critic is not None:
            return await critic.critique(state, observation)
        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.ON_TRACK,
            lesson=None,
        )


__all__ = ["StandardCognitiveReflectionPipeline", "StandardCognitiveThinkPipeline"]
