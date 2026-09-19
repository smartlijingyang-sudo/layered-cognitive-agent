"""Shared composition of the standard cognitive Brain factory.

Both ``default`` and ``modular`` registry aliases intentionally expose the
same profile-selected cognitive primitive set. Keeping that closure here
makes the alias relationship explicit and prevents the two plugin
declarations from silently drifting in their gate, reasoner, classifier,
or pipeline wiring.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from lca.contracts.capabilities import (
    BRAINS,
    COGNITIVE_REFLECTION_PIPELINE,
    COGNITIVE_THINK_PIPELINE,
    PROMPT_ASSEMBLER,
    PROMPT_SECTION_REGISTRY,
    PROMPT_TEMPLATE_SELECTOR,
)
from lca.contracts.mechanisms.capability.capability import MissingCapabilityError
from lca.contracts.protocols import BrainFactory, DecisionGate

if TYPE_CHECKING:
    from lca.cognition.brain.gate.service import GateService
    from lca.harness.plugin_api import PluginContext


STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS: tuple[str, ...] = (
    BRAINS.key,
    "gates",
    "critic.simple",
    "reasoner.prompt",
    "decision_classifier",
    COGNITIVE_THINK_PIPELINE.key,
    COGNITIVE_REFLECTION_PIPELINE.key,
    PROMPT_ASSEMBLER.key,
    PROMPT_SECTION_REGISTRY.key,
    PROMPT_TEMPLATE_SELECTOR.key,
)
"""The complete, profile-selected dependency closure of the standard Brain."""


def _agent_gate_factory_from(
    ctx: PluginContext,
) -> Callable[[], DecisionGate | None] | None:
    """Resolve the profile-selected Think guard chain, fail-soft.

    The Brain aliases require the ``gates`` capability, but a profile may
    legitimately omit the ``gates.chain.sequential`` assembler contribution.
    Such profiles keep the pre-PR-5 behavior (``agent_gates=None``) instead
    of failing Brain construction; only an actually assembled chain is
    exposed to the ``concept.decision.enforce`` guard nodes.
    """

    try:
        gates = cast("GateService", ctx.require("gates"))
    except KeyError:
        return None

    def _build() -> DecisionGate | None:
        try:
            return gates.assemble()
        except MissingCapabilityError:
            return None

    return _build


def build_standard_cognitive_brain_factory(ctx: PluginContext) -> BrainFactory:
    """Close selected cognitive primitives into the shared standard Brain factory.

    The plugin declaration owns selection through ``requires``; this helper
    only consumes that declared closure and never supplies implementation
    fallbacks. Each registry alias receives a new factory with the same
    immutable profile configuration.
    """

    from lca.cognition.brain.pipeline.default_factory import SimpleBrainFactory

    return SimpleBrainFactory(
        agent_gate_factory=_agent_gate_factory_from(ctx),
        classifier=ctx.require("decision_classifier"),
        critic_factory=ctx.require("critic.simple"),
        reasoner_cls=ctx.require("reasoner.prompt"),
        assembler=ctx.require(PROMPT_ASSEMBLER.key),
        selector=ctx.require(PROMPT_TEMPLATE_SELECTOR.key),
        section_registry=ctx.require(PROMPT_SECTION_REGISTRY.key),
        think_pipeline=ctx.require(COGNITIVE_THINK_PIPELINE.key),
        reflection_pipeline=ctx.require(COGNITIVE_REFLECTION_PIPELINE.key),
    )


__all__ = [
    "STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS",
    "build_standard_cognitive_brain_factory",
]
