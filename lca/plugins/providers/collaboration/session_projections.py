"""Default Provider for profile-selected Session projection registries."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.harness.state.projection import (
    SessionProjectionRegistry,
    SessionProjectionRegistryFactory,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.projection.web import ActivityProjection, ConversationProjection, TaskProjection
from lca.harness.skills import SkillsProjection


class Config(BaseModel):
    """Default Session projection provider configuration."""

    model_config = {"extra": "forbid"}


class InMemoryWebProjectionRegistryFactory(SessionProjectionRegistryFactory):
    """Create the default in-memory registry with all carrier-facing views."""

    def create(self) -> SessionProjectionRegistry:
        registry = InMemoryProjectionRegistry()
        registry.register(ConversationProjection())
        registry.register(ActivityProjection())
        registry.register(TaskProjection())
        registry.register(SkillsProjection())
        return registry


@plugin(
    id="lca-session-projection-memory-provider",
    requires=[],
    provides=["session_projection_registry_factory"],
    implements=[SessionProjectionRegistryFactory],
    layer="L0",
    effects="memory",
    kind=PluginKind.PROVIDER,
    description="Provide in-memory Session projections for Gateway conversation, activity, task, and skills views.",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-session-projection-memory-provider.checked",
                "lca-session-projection-memory-provider.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("session_projection_registry_factory",),
        emits=("session_projection_registry_factory.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default Session projection-registry factory."""

    del config
    ctx.provide("session_projection_registry_factory", InMemoryWebProjectionRegistryFactory())


__all__ = ["Config", "InMemoryWebProjectionRegistryFactory", "setup"]
