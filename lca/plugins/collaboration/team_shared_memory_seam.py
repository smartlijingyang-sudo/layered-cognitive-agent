"""Default provider for the Team shared-memory selection capability.

Shared-memory selection precedes member assembly, so it is an independent Team
backend decision.  Registering it as its own provider keeps the choice visible
in the compiled plugin tree and lets profiles replace it without changing the
Team seam factory or the communication assembler.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import TEAM_SHARED_MEMORY_RESOLVER
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.memory import MemoryLayer
from lca.contracts.protocols.collaboration.orchestration import SharedMemoryStore
from lca.contracts.protocols.collaboration.team_seam import TeamSharedMemoryResolverProtocol
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.spec import TeamSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default Team shared-memory resolver has no configuration."""

    model_config = {"extra": "forbid"}


class DefaultTeamSharedMemoryResolver(TeamSharedMemoryResolverProtocol):
    """Create the default Team-owned memory store from the Team specification."""

    def resolve(
        self,
        spec: TeamSpec,
        *,
        shared_layers: tuple[MemoryLayer, ...] = (),
    ) -> SharedMemoryStore | None:
        """Return no store when the Team did not declare shared memory layers."""

        from lca.cognition.memory.team_shared_memory import TeamSharedMemoryStore

        layers = shared_layers or tuple(spec.shared_memory_layers)
        return TeamSharedMemoryStore(list(layers)) if layers else None


@plugin(
    id="lca-team-shared-memory-default",
    provides=[TEAM_SHARED_MEMORY_RESOLVER.key],
    requires=[],
    implements=[TeamSharedMemoryResolverProtocol],
    layer="L3",
    effects="none",
    description="Provide the default Team shared-memory resolver.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-team-shared-memory-default.checked",
                "lca-team-shared-memory-default.served",
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
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the profile-selected shared-memory resolver to the Team seam."""

    del config
    ctx.provide(TEAM_SHARED_MEMORY_RESOLVER.key, DefaultTeamSharedMemoryResolver())


__all__ = ["Config", "DefaultTeamSharedMemoryResolver", "setup"]
