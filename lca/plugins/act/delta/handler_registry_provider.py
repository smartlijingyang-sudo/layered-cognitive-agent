"""Delta handler registry and provider-owned default registration.

This module owns only the registry seam and the default operation-to-handler
assembly. Individual delta handlers remain in ``delta_handlers`` so their
state-folding behavior stays local and independently navigable.
"""

from __future__ import annotations

from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.infrastructure.handler.registry import make_inmemory_registry

# Neutral registry keyed by the Reducer operation name; provider installs defaults.
InMemoryDeltaHandlerRegistry = make_inmemory_registry("delta handler", DeltaHandlerRegistry)


def register_default_delta_handlers(registry: DeltaHandlerRegistry) -> None:
    """Register the provider-owned handlers on ``registry``."""
    from lca.plugins.act.delta.handlers_provider import (
        ActivationDeltaHandler,
        ErrorDeltaHandler,
        MemoryDeltaHandler,
        PausedDeltaHandler,
        PerceptionDeltaHandler,
        ResumeDeltaHandler,
        SkillRouteDeltaHandler,
        StepDeltaHandler,
        StopDeltaHandler,
        TurnDeltaHandler,
    )

    registry.register("step", StepDeltaHandler())
    registry.register("perception", PerceptionDeltaHandler())
    registry.register("turn", TurnDeltaHandler())
    registry.register("skill_route", SkillRouteDeltaHandler())
    registry.register("activation", ActivationDeltaHandler())
    registry.register("memory", MemoryDeltaHandler())
    registry.register("stop", StopDeltaHandler())
    registry.register("error", ErrorDeltaHandler())
    registry.register("resume", ResumeDeltaHandler())
    registry.register("paused", PausedDeltaHandler())


class DefaultDeltaHandlerRegistry(InMemoryDeltaHandlerRegistry):  # type: ignore[valid-type, misc]
    """Compatibility factory with the provider's default handler set."""

    def __init__(self) -> None:
        super().__init__()
        register_default_delta_handlers(self)


__all__ = [
    "DefaultDeltaHandlerRegistry",
    "InMemoryDeltaHandlerRegistry",
    "register_default_delta_handlers",
]
