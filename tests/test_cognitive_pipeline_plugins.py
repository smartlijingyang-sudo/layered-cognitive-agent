"""Substitution tests for the Think and Reflect cognitive primitives."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lca.cognition.brain.modular_brain import ModularBrain
from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import (
    COGNITIVE_REFLECTION_PIPELINE,
    COGNITIVE_THINK_PIPELINE,
)
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols import (
    CognitiveReflectionPipeline,
    CognitiveThinkPipeline,
)
from lca.harness.plugin_declaration import definition_from_plugin
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.brain._standard_factory import STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS

REPO = Path(__file__).resolve().parents[1]


class _ThinkPipeline:
    """Custom primitive that records its wiring without running an LLM."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        self.received: dict[str, object] | None = None

    async def decide(self, **kwargs: object) -> Decision:
        self.received = kwargs
        return self.decision


class _ReflectionPipeline:
    """Custom primitive that records its wiring without invoking a critic."""

    def __init__(self, reflection: Reflection) -> None:
        self.reflection = reflection
        self.received: dict[str, object] | None = None

    async def reflect(self, **kwargs: object) -> Reflection:
        self.received = kwargs
        return self.reflection


def _state() -> AgentState:
    return AgentState(
        trace_id="trace-cognitive-pipeline", task="exercise primitive", budget=Budget()
    )


def test_standard_profile_declares_independent_cognitive_pipeline_providers() -> None:
    """The default production profile binds both subflows through plugin declarations."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert (
        COGNITIVE_THINK_PIPELINE.key
        in by_id["lca-cognitive-think-pipeline-standard"].provided_capability_keys
    )
    assert (
        COGNITIVE_REFLECTION_PIPELINE.key
        in by_id["lca-cognitive-reflection-pipeline-standard"].provided_capability_keys
    )
    brain_requires = by_id["lca-brain-simple"].required_capability_keys
    assert COGNITIVE_THINK_PIPELINE.key in brain_requires
    assert COGNITIVE_REFLECTION_PIPELINE.key in brain_requires


def test_standard_cognitive_plugins_share_a_g5_primitive_boundary() -> None:
    """Brain aliases and subflow providers remain one explicitly typed G5 closure."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    for plugin_id in (
        "lca-brain-simple",
        "lca-cognitive-think-pipeline-standard",
        "lca-cognitive-reflection-pipeline-standard",
    ):
        assert by_id[plugin_id].functional_group is FunctionalGroup.G5_COGNITION

    from lca.plugins.brain.modular import setup as modular_setup

    modular_definition = definition_from_plugin(modular_setup)
    assert modular_definition.functional_group is FunctionalGroup.G5_COGNITION
    assert (
        by_id["lca-brain-simple"].required_capability_keys
        == STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS
    )
    assert (
        modular_definition.required_capability_keys == STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS
    )


@pytest.mark.asyncio
async def test_modular_brain_delegates_each_phase_to_selected_cognitive_primitive() -> None:
    """Changing either primitive does not require changing the Brain facade."""

    decision = Decision(
        decision_id="decision-custom-pipeline",
        action_type="respond",
        rationale="custom Think primitive selected",
        confidence=1.0,
        response_text="delegated",
    )
    reflection = Reflection(
        reflection_id="reflection-custom-pipeline",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson="custom Reflect primitive selected",
    )
    think_pipeline = _ThinkPipeline(decision)
    reflection_pipeline = _ReflectionPipeline(reflection)
    state = _state()
    observation = Observation(observation_id="observation", success=True, payload="ok")
    reasoner = MagicMock()
    classifier = MagicMock()
    critic = MagicMock()

    assert isinstance(think_pipeline, CognitiveThinkPipeline)
    assert isinstance(reflection_pipeline, CognitiveReflectionPipeline)
    brain = ModularBrain(
        reasoner=reasoner,
        classifier=classifier,
        critic=critic,
        think_pipeline=think_pipeline,
        reflection_pipeline=reflection_pipeline,
    )

    assert await brain.think(state) is decision
    assert await brain.reflect(state, observation) is reflection
    assert think_pipeline.received is not None
    assert reflection_pipeline.received is not None
    assert think_pipeline.received["state"] is state
    assert think_pipeline.received["reasoner"] is reasoner
    assert reflection_pipeline.received["observation"] is observation
    assert reflection_pipeline.received["critic"] is critic
    reasoner.generate_thoughts.assert_not_called()
    classifier.classify.assert_not_called()
    critic.critique.assert_not_called()


def test_modular_brain_no_longer_owns_fixed_think_or_reflect_implementation() -> None:
    """The facade delegates; the standard sequence and null fallback live in providers."""

    source = (REPO / "lca/cognition/brain/modular_brain.py").read_text(encoding="utf-8")

    assert "generate_thoughts(" not in source
    assert "_default_reflect" not in source
    assert "_think_pipeline.decide(" in source
    assert "_reflection_pipeline.reflect(" in source
