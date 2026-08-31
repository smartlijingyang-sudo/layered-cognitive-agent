"""Default tracing contribution for declarative phase observation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import PHASE_OBSERVER_REGISTRY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.phase_observation import (
    PhaseObserver,
    PhaseObserverContribution,
    PhaseObserverRegistry,
)
from lca.harness.declarative.lifecycle.phase_observation import TracingPhaseObserver
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Configure the tracing contribution's deterministic precedence."""

    priority: int = Field(default=100, ge=0)
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-phase-observer-tracing-provider",
    Config=Config,
    provides=[],
    requires=[PHASE_OBSERVER_REGISTRY.key],
    implements=[PhaseObserver],
    layer="L2",
    effects="none",
    description="Contribute standard tracing as a read-only declarative phase observer.",
    test_suite="tests/declarative/test_phase_observer_plugins.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-phase-observer-tracing-provider.checked",
                "lca-phase-observer-tracing-provider.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Register tracing without becoming the single runtime observer provider."""

    if not isinstance(config, Config):
        raise TypeError("phase observer tracing config must be Config")
    registry = ctx.require(PHASE_OBSERVER_REGISTRY)
    if not isinstance(registry, PhaseObserverRegistry):
        raise TypeError("phase_observer_registry must implement PhaseObserverRegistry")
    registry.register(
        PhaseObserverContribution(
            id="tracing",
            observer=TracingPhaseObserver(),
            priority=config.priority,
        )
    )


__all__ = ["Config", "setup"]
