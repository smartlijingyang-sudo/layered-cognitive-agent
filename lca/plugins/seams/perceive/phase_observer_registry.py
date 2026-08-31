"""Phase-observer contribution registry seam.

The seam provides only an empty registry.  Provider plugins explicitly register
read-only observers during profile boot, while the single ``phase_observer``
provider freezes those contributions into the runtime binding.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import PHASE_OBSERVER_REGISTRY
from lca.contracts.protocols.journal.phase_observation import PhaseObserverRegistry
from lca.harness.declarative.lifecycle.phase_observation import InMemoryPhaseObserverRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


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


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-phase-observer-registry-seam.checked', 'lca-phase-observer-registry-seam.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Mount the empty contribution registry; providers supply all behavior."""

    del config
    ctx.provide(PHASE_OBSERVER_REGISTRY.key, InMemoryPhaseObserverRegistry())


__all__ = ["Config", "InMemoryPhaseObserverRegistry", "PhaseObserverRegistry", "setup"]
