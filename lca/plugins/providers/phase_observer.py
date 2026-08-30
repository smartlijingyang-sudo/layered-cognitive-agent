"""Profile-selected composite provider for declarative phase observation.

The provider remains the only producer of the runtime's ``phase_observer``
capability.  Individual behaviors arrive as independent boot-time contributions
through a neutral registry, keeping observation composable without allowing it
to enter the declarative transaction's control path.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lca.contracts.capabilities import PHASE_OBSERVER, PHASE_OBSERVER_REGISTRY
from lca.contracts.protocols.journal.phase_observation import PhaseObserver, PhaseObserverRegistry
from lca.harness.declarative.phase_observation import (
    CompositePhaseObserver,
    ObserverFailureMode,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Configure the policy for failures in passive phase observers."""

    failure_mode: Literal["fail_open", "fail_closed"] = "fail_open"
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-phase-observer-provider",
    Config=Config,
    provides=[PHASE_OBSERVER.key],
    requires=[PHASE_OBSERVER_REGISTRY.key],
    implements=[PhaseObserver],
    layer="L2",
    effects="none",
    description="Freeze contributed read-only phase observers into the runtime observer.",
    test_suite="tests/declarative/test_phase_observer_plugins.py",
    kind=PluginKind.COMPOSITE,
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Build one immutable observer for every runtime created from this profile."""

    if not isinstance(config, Config):
        raise TypeError("phase observer config must be Config")
    registry = ctx.require(PHASE_OBSERVER_REGISTRY)
    if not isinstance(registry, PhaseObserverRegistry):
        raise TypeError("phase_observer_registry must implement PhaseObserverRegistry")
    ctx.provide(
        PHASE_OBSERVER.key,
        CompositePhaseObserver(
            registry.snapshot(),
            failure_mode=ObserverFailureMode(config.failure_mode),
        ),
    )


__all__ = ["Config", "setup"]
