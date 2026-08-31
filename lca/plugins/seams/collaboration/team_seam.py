"""The Team seam and its default orchestration factory.

The public ``team_seam`` capability remains the single composition seam used
by ``TeamComposer``. Its default factory deliberately delegates the two
independent backend decisions to deep collaborators:

* shared-memory selection happens before members are assembled;
* transport plus invocation close together after members are available.

This preserves member single-assembly while keeping future backend changes
local to the decision they affect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    TEAM_COMMUNICATION,
    TEAM_SEAM,
    TEAM_SHARED_MEMORY_RESOLVER,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.models.core.memory import MemoryLayer
from lca.contracts.protocols.collaboration.agent import AgentUnit
from lca.contracts.protocols.collaboration.team_seam import (
    TeamCommunicationAssemblerProtocol,
    TeamSeamFactoryProtocol,
    TeamSharedMemoryResolverProtocol,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.spec import TeamSpec
from lca.contracts.protocols.runtime.infra import AgentTransport
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.contracts.protocols import MemberInvoker, SharedMemoryStore


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@dataclass(frozen=True, slots=True)
class TeamSeam:
    """The three Team backend collaborators consumed by ``TeamComposer``."""

    shared_memory: SharedMemoryStore | None
    transport: AgentTransport
    invoker: MemberInvoker


@plugin(
    id="lca-team-seam-seam",
    provides=[TEAM_SEAM.key],
    requires=[TEAM_COMMUNICATION.key, TEAM_SHARED_MEMORY_RESOLVER.key],
    implements=[TeamSeamFactoryProtocol],
    layer="L3",
    effects="none",
    description="Provide the TeamSeam Definition service for TeamComposer.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-team-seam-seam.checked", "lca-team-seam-seam.served")
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
    del config
    ctx.provide(
        TEAM_SEAM.key,
        TeamSeamFactory(
            shared_memory_resolver=require_capability(ctx, TEAM_SHARED_MEMORY_RESOLVER.key),
            communication_assembler=require_capability(ctx, TEAM_COMMUNICATION.key),
        ),
    )


class TeamSeamFactory(TeamSeamFactoryProtocol):
    """Orchestrate Team backend decisions without owning their implementations.

    ``TeamComposer`` continues to replace this factory as one public seam. A
    A profile must explicitly provide both backend collaborators, making their
    independent selections visible in the compiled plugin tree. Shared-memory
    selection cannot affect communication construction, and vice versa.
    """

    def __init__(
        self,
        *,
        shared_memory_resolver: TeamSharedMemoryResolverProtocol,
        communication_assembler: TeamCommunicationAssemblerProtocol,
    ) -> None:
        self._shared_memory_resolver = shared_memory_resolver
        self._communication_assembler = communication_assembler

    def resolve_shared_memory(
        self,
        spec: TeamSpec,
        *,
        shared_layers: tuple[MemoryLayer, ...] = (),
    ) -> SharedMemoryStore | None:
        """Resolve shared memory before the one member-assembly pass."""

        return self._shared_memory_resolver.resolve(spec, shared_layers=shared_layers)

    def build(
        self,
        spec: TeamSpec,
        *,
        members: tuple[AgentUnit, ...],
        shared_memory: SharedMemoryStore | None,
    ) -> TeamSeam:
        """Close compatible communication after members have been assembled."""

        communication = self._communication_assembler.assemble(spec, members=members)
        return TeamSeam(
            shared_memory=shared_memory,
            transport=communication.transport,
            invoker=communication.invoker,
        )


__all__ = ["Config", "TeamSeam", "TeamSeamFactory", "setup"]
