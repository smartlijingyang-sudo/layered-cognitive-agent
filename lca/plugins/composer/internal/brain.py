"""Think-cluster assembly helpers for plan-bound graph composition."""

from __future__ import annotations

from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY, BRAINS
from lca.contracts.mechanisms import consume
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols import (
    Brain,
    BrainPromptCatalog,
    BrainPromptCatalogFactory,
    DecisionGate,
    LLMAdapter,
)
from lca.contracts.protocols.spec import AgentSpec
from lca.infrastructure.observability.adapters import TelemetryLLMAdapter
from lca.cognition.brain.modular_brain import ModularBrain
from lca.cognition.brain.reasoner import PromptReasoner
from lca.plugins.composer.internal.skill_store import active_skill_store


def instrument_llm(llm: LLMAdapter) -> LLMAdapter:
    """Return the model adapter behind the standard telemetry decorator."""

    inner = llm._inner if isinstance(llm, TelemetryLLMAdapter) else llm
    return TelemetryLLMAdapter(inner)


def resolve_brain(spec: AgentSpec, llm: LLMAdapter, *, scope: object) -> Brain:
    """Build the selected Brain with its model-visible prompt catalog.

    The active skill provider is resolved only for this Think-cluster concern,
    keeping skill discovery and prompt rendering out of unrelated graph
    composers.
    """

    if not isinstance(spec.brain, str):
        return spec.brain

    brains = require_capability(scope, BRAINS.key)
    try:
        factory = brains.resolve(spec.brain)
    except KeyError as exc:
        raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {brains.names()}") from exc

    prompt_catalog_factory = require_capability(scope, BRAIN_PROMPT_CATALOG_FACTORY.key)
    if not isinstance(prompt_catalog_factory, BrainPromptCatalogFactory):
        raise TypeError(
            "brain_prompt_catalog_factory must implement BrainPromptCatalogFactory, "
            f"got {type(prompt_catalog_factory).__name__}"
        )
    prompt_catalog = prompt_catalog_factory.create(
        skill_store=active_skill_store(scope),
        tools=spec.tools,
    )
    if not isinstance(prompt_catalog, BrainPromptCatalog):
        raise TypeError(
            "brain_prompt_catalog_factory.create must return BrainPromptCatalog, "
            f"got {type(prompt_catalog).__name__}"
        )
    brain = factory(
        consume("llm", llm, PromptReasoner),
        spec.profile,
        prompt_catalog.render_tools_xml(),
        tools=list(spec.tools),
        available_skills=prompt_catalog.render_brain_skills(),
    )
    if not isinstance(brain, Brain):
        raise TypeError(
            f"brain factory {spec.brain!r} produced {type(brain).__name__}, expected Brain"
        )
    return brain


def apply_lead_brain(brain: Brain, decision_gate: DecisionGate) -> Brain:
    """Return a lead Brain whose closed-set gate is installed explicitly."""

    if not isinstance(brain, ModularBrain):
        raise TypeError(f"lead composition requires ModularBrain (got {type(brain).__name__})")
    return ModularBrain(
        reasoner=brain.reasoner,
        reducer=brain.reducer,
        classifier=brain.classifier,
        critic=brain.critic,
        skill_router=brain.skill_router,
        decision_gate=decision_gate,
        agent_gates=brain.agent_gates,
        think_pipeline=brain.think_pipeline,
        reflection_pipeline=brain.reflection_pipeline,
    )


__all__ = ["apply_lead_brain", "instrument_llm", "resolve_brain"]
