"""``ModularBrain``——面向阶段执行器的稳定认知门面。

Think 与 Reflect 的具体编排属于可替换的认知原语，并由组合层显式注入。
``ModularBrain`` 只保留对外 ``Brain`` 协议和已选择协作者的闭合，不再拥有固定的
子步骤顺序或私有的反思回退策略。
"""

from __future__ import annotations

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    Brain,
    Critic,
    DecisionGate,
    Reasoner,
    Reducer,
    SkillRouter,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.contracts.protocols.think.cognitive_pipeline import (
    CognitiveReflectionPipeline,
    CognitiveThinkPipeline,
)


class ModularBrain(Brain):
    """Close profile-selected collaborators behind the stable ``Brain`` protocol.

    Production factories must pass both cognitive pipelines from the booted
    capability graph. The optional standalone fallback keeps direct in-process
    construction compatible for focused unit tests and custom callers that do
    not boot a profile; it is never selected by the production factory.
    """

    def __init__(
        self,
        reasoner: Reasoner,
        classifier: DecisionClassifier,
        critic: Critic | None = None,
        skill_router: SkillRouter | None = None,
        decision_gate: DecisionGate | None = None,
        agent_gates: DecisionGate | None = None,
        reducer: Reducer | None = None,
        think_pipeline: CognitiveThinkPipeline | None = None,
        reflection_pipeline: CognitiveReflectionPipeline | None = None,
    ) -> None:
        self.reasoner = reasoner
        self.critic = critic
        self.skill_router = skill_router
        self._decision_gate: DecisionGate | None = decision_gate
        self._agent_gates: DecisionGate | None = agent_gates
        self.reducer = reducer
        self.classifier = classifier
        self._think_pipeline = think_pipeline or _standalone_think_pipeline()
        self._reflection_pipeline = reflection_pipeline or _standalone_reflection_pipeline()
        if not isinstance(self._think_pipeline, CognitiveThinkPipeline):
            raise TypeError(
                "think_pipeline must implement CognitiveThinkPipeline, got "
                f"{type(self._think_pipeline).__name__}"
            )
        if not isinstance(self._reflection_pipeline, CognitiveReflectionPipeline):
            raise TypeError(
                "reflection_pipeline must implement CognitiveReflectionPipeline, got "
                f"{type(self._reflection_pipeline).__name__}"
            )

    @property
    def agent_gates(self) -> DecisionGate | None:
        """Return the immutable-plan-bound Think guard chain."""

        return self._agent_gates

    @property
    def think_pipeline(self) -> CognitiveThinkPipeline:
        """Return the profile-selected Think primitive for composition reuse."""

        return self._think_pipeline

    @property
    def reflection_pipeline(self) -> CognitiveReflectionPipeline:
        """Return the profile-selected Reflect primitive for composition reuse."""

        return self._reflection_pipeline

    async def think(self, state: AgentState) -> Decision:
        """Delegate one Think phase to the selected cognitive primitive."""

        # PR-3.2: spine envelope for the brain.think execution point.
        from lca.plugins.events.publishers.spine_reflector_cognition import (
            emit_brain_think_end,
            emit_brain_think_start,
        )

        state_id = state.trace_id
        emit_brain_think_start(state_id=state_id)
        try:
            decision = await self._think_pipeline.decide(
                state=state,
                reasoner=self.reasoner,
                classifier=self.classifier,
                skill_router=self.skill_router,
                decision_gate=self._decision_gate,
                agent_gates=self._agent_gates,
                reducer=self.reducer,
            )
        except BaseException:
            emit_brain_think_end(state_id=state_id, outcome="failure")
            raise
        emit_brain_think_end(state_id=state_id, outcome="success")
        return decision

    async def reflect(self, state: AgentState, observation: Observation) -> Reflection:
        """Delegate one Reflect phase to the selected cognitive primitive."""

        return await self._reflection_pipeline.reflect(
            state=state,
            observation=observation,
            critic=self.critic,
        )


def _standalone_think_pipeline() -> CognitiveThinkPipeline:
    """Return the legacy-compatible default for callers outside profile boot."""

    from lca.cognition.brain.cognitive_pipeline import StandardCognitiveThinkPipeline

    return StandardCognitiveThinkPipeline()


def _standalone_reflection_pipeline() -> CognitiveReflectionPipeline:
    """Return the legacy-compatible default for callers outside profile boot."""

    from lca.cognition.brain.cognitive_pipeline import StandardCognitiveReflectionPipeline

    return StandardCognitiveReflectionPipeline()


__all__ = ["ModularBrain"]
