"""Explicit in-process defaults used only by declarative runtime fixtures."""

from __future__ import annotations

from lca.contracts.protocols import ArtifactClosure
from lca.contracts.protocols.act.effect_handler import EffectHandlerRegistry
from lca.contracts.protocols.journal.idempotency import IdempotencyStore
from lca.contracts.protocols.session.resume_input import ResumeInputAdapter
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.plugins.providers.act.delta_handlers import DefaultDeltaHandlerRegistry
from lca.plugins.providers.act.effect_handlers import (
    InMemoryEffectHandlerRegistry,
    register_default_effect_handlers,
)
from lca.plugins.providers.journal.artifact_closure import DefaultArtifactClosure
from lca.runtime.idempotency_fixtures import InMemoryFixtureIdempotencyStore
from lca.runtime.resume_input import HumanAnswerResumeInputAdapter


def effect_handlers() -> EffectHandlerRegistry:
    """Create the provider-owned default effect handlers for fixtures."""

    registry = InMemoryEffectHandlerRegistry()
    register_default_effect_handlers(registry)
    return registry


def delta_handlers() -> DeltaHandlerRegistry:
    """Create the provider-owned default delta handlers for fixtures."""

    return DefaultDeltaHandlerRegistry()


def artifact_closure() -> ArtifactClosure:
    """Create the default artifact-closure provider for fixtures."""

    return DefaultArtifactClosure()


def resume_input_adapter() -> ResumeInputAdapter:
    """Create the default human-answer adapter for fixtures."""

    return HumanAnswerResumeInputAdapter()


def idempotency_store() -> IdempotencyStore:
    """Create the in-process idempotency store for fixtures."""

    return InMemoryFixtureIdempotencyStore()


__all__ = [
    "artifact_closure",
    "delta_handlers",
    "effect_handlers",
    "idempotency_store",
    "resume_input_adapter",
]
