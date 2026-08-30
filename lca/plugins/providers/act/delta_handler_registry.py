"""Delta handler registry and provider-owned default registration.

This module owns only the registry seam and the default operation-to-handler
assembly. Individual delta handlers remain in ``delta_handlers`` so their
state-folding behavior stays local and independently navigable.
"""

from __future__ import annotations

from lca.contracts.protocols.state.delta_handler import DeltaHandler, DeltaHandlerRegistry
from lca.infrastructure.handler_registry import UniqueOperationRegistry


class InMemoryDeltaHandlerRegistry(UniqueOperationRegistry[DeltaHandler], DeltaHandlerRegistry):
    """Neutral registry keyed by the Reducer operation name."""

    def __init__(self) -> None:
        super().__init__("delta handler")

    def register(self, operation: str, handler: DeltaHandler) -> None:
        """Register the unique owner of a Reducer operation."""
        self._register(operation, handler)

    def resolve(self, operation: str) -> DeltaHandler | None:
        """Resolve the handler for a Reducer operation."""
        return self._resolve(operation)

    def registered_delta_operations(self) -> tuple[str, ...]:
        """Return a stable snapshot of registered Reducer operations."""
        return self._registered_operations()


def register_default_delta_handlers(registry: DeltaHandlerRegistry) -> None:
    """Register the provider-owned handlers on ``registry``."""
    from lca.plugins.providers.act.delta_handlers import (
        ActivationDeltaHandler,
        ArtifactClosureDeltaHandler,
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
    registry.register("artifact_closure", ArtifactClosureDeltaHandler())
    registry.register("paused", PausedDeltaHandler())


class DefaultDeltaHandlerRegistry(InMemoryDeltaHandlerRegistry):
    """Compatibility factory with the provider's default handler set."""

    def __init__(self) -> None:
        super().__init__()
        register_default_delta_handlers(self)


__all__ = [
    "DefaultDeltaHandlerRegistry",
    "InMemoryDeltaHandlerRegistry",
    "register_default_delta_handlers",
]
