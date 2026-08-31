"""Build a modular Brain from collaborators selected by composition.

``SimpleBrainFactory`` owns only the construction of one ``ModularBrain``. It
must not choose a Critic, Reasoner, Think pipeline, or Reflect pipeline on
behalf of the composition root: those choices are declared by the selected
plugins and injected explicitly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from lca.cognition.brain.modular_brain import ModularBrain
from lca.cognition.brain.reasoner import PromptReasoner
from lca.contracts.mechanisms import consume
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import (
    Brain,
    Critic,
    DecisionGate,
    LLMAdapter,
    Tool,
)
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.contracts.protocols.think.cognitive_pipeline import (
    CognitiveReflectionPipeline,
    CognitiveThinkPipeline,
)


class SimpleBrainFactory:
    """Construct the default ``ModularBrain`` from an explicit dependency set.

    The composition root selects the gate chain, decision classifier, critic,
    reasoner, and both cognitive subflow providers. Keeping these selections
    outside Layer 1 makes a configured Brain reproducible from its plugin graph:
    changing a primitive requires a changed declaration instead of relying on a
    hidden Python fallback.

    This factory deliberately has no ``synthesizer_factory`` argument. A
    synthesizer is not consumed while constructing ``ModularBrain``; exposing
    it here would create a misleading seam whose configuration has no runtime
    effect.
    """

    def __init__(
        self,
        *,
        agent_gate_factory: Callable[[], DecisionGate],
        classifier: DecisionClassifier,
        critic_factory: Callable[[], Critic],
        reasoner_cls: type[PromptReasoner],
        reasoner_templates: Mapping[str, str],
        think_pipeline: CognitiveThinkPipeline,
        reflection_pipeline: CognitiveReflectionPipeline,
    ) -> None:
        self._agent_gate_factory = agent_gate_factory
        self._classifier = classifier
        self._critic_factory = critic_factory
        self._reasoner_cls = reasoner_cls
        self._reasoner_templates = dict(reasoner_templates)
        if not isinstance(think_pipeline, CognitiveThinkPipeline):
            raise TypeError(
                "think_pipeline must implement CognitiveThinkPipeline, got "
                f"{type(think_pipeline).__name__}"
            )
        if not isinstance(reflection_pipeline, CognitiveReflectionPipeline):
            raise TypeError(
                "reflection_pipeline must implement CognitiveReflectionPipeline, got "
                f"{type(reflection_pipeline).__name__}"
            )
        self._think_pipeline = think_pipeline
        self._reflection_pipeline = reflection_pipeline

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        tools: list[Tool] | None = None,
        available_skills: str = "",
    ) -> Brain:
        reasoner = self._reasoner_cls(
            consume("llm", llm, PromptReasoner),
            role_profile,
            tools_desc,
            tools=tools,
            templates=self._reasoner_templates,
            available_skills=available_skills,
        )
        return ModularBrain(
            reasoner=reasoner,
            critic=self._critic_factory(),
            agent_gates=self._agent_gate_factory(),
            classifier=self._classifier,
            think_pipeline=self._think_pipeline,
            reflection_pipeline=self._reflection_pipeline,
        )
