"""Default Provider for the profile-selected durable Session fact stream."""

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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.session.session_persistence import SessionPersistenceFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.harness.session.persistence import JsonlSessionPersistenceFactory


class Config(BaseModel):
    """Default session-persistence provider configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-session-persistence-jsonl-provider",
    requires=[],
    provides=["session_persistence_factory"],
    implements=[SessionPersistenceFactory],
    layer="L0",
    effects="filesystem",
    kind=PluginKind.PROVIDER,
    description="Provide JSONL persistence for durable Session fact streams.",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-session-persistence-jsonl-provider.checked",
                "lca-session-persistence-jsonl-provider.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("session_persistence_factory",),
        emits=("session_persistence_factory.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default Session persistence factory."""

    del config
    ctx.provide("session_persistence_factory", JsonlSessionPersistenceFactory())


__all__ = ["Config", "setup"]
