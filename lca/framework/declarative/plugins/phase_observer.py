"""Default ``phase_observer`` capability provider.

Registers the no-op :class:`NullPhaseObserver` so the interpreter can
bracket every phase without forcing a profile to contribute at least one
real observer.  Production profiles are expected to swap this with a
composite observer that fans out to telemetry and audit sinks.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.journal.phase.observation import PhaseObserver
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default null phase observer has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="declarative.phase_observer",
    requires=[],
    provides=["phase_observer"],
    implements=[PhaseObserver],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default null PhaseObserver so declarative profiles have a "
        "passive observation seam until a telemetry-backed observer replaces it."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "declarative.phase_observer.checked",
                "declarative.phase_observer.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("phase_observer",),
        emits=("phase_observer.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default no-op PhaseObserver to runtime assembly."""

    del config
    ctx.provide("phase_observer", NullPhaseObserver())


__all__ = ["Config", "setup"]
