"""Phase-observer contribution registry seam.

The seam provides only an empty registry.  Provider plugins explicitly register
read-only observers during profile boot, while the single ``phase_observer``
provider freezes those contributions into the runtime binding.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import PHASE_OBSERVER_REGISTRY
from lca.contracts.protocols.phase_observation import PhaseObserverRegistry
from lca.harness.declarative.phase_observation import InMemoryPhaseObserverRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The neutral registry has no configurable behavior."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-phase-observer-registry-seam",
    Config=Config,
    provides=[PHASE_OBSERVER_REGISTRY.key],
    requires=[],
    implements=[PhaseObserverRegistry],
    layer="L2",
    effects="none",
    description="Provide the neutral registry for read-only phase observer contributions.",
    test_suite="tests/declarative/test_phase_observer_plugins.py",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Mount the empty contribution registry; providers supply all behavior."""

    del config
    ctx.provide(PHASE_OBSERVER_REGISTRY.key, InMemoryPhaseObserverRegistry())


__all__ = ["Config", "InMemoryPhaseObserverRegistry", "PhaseObserverRegistry", "setup"]
