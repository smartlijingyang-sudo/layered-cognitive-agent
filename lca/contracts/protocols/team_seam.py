from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.protocols.agent import AgentUnit
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.spec import TeamSpec

if TYPE_CHECKING:
    from lca.contracts.protocols.orchestration import MemberInvoker, SharedMemoryStore


@dataclass(frozen=True, slots=True)
class TeamCommunication:
    """The transport and invoker selected after Team members are assembled.

    The pair changes together: an invoker interprets the transport protocol it
    receives. Keeping them in one value prevents a Team seam from combining a
    compatible transport with an unrelated invocation implementation.
    """

    transport: AgentTransport
    invoker: MemberInvoker


@runtime_checkable
class TeamSharedMemoryResolverProtocol(Protocol):
    """Select the Team-owned shared-memory backend before member assembly."""

    def resolve(
        self,
        spec: TeamSpec,
        *,
        shared_layers: tuple[MemoryLayer, ...] = (),
    ) -> SharedMemoryStore | None: ...


@runtime_checkable
class TeamCommunicationAssemblerProtocol(Protocol):
    """Close transport and member invocation after members are available."""

    def assemble(
        self,
        spec: TeamSpec,
        *,
        members: tuple[AgentUnit, ...],
    ) -> TeamCommunication: ...


@runtime_checkable
class TeamSeamFactoryProtocol(Protocol):
    """Resolve Team collaborators without forcing members to be rebuilt.

    Shared memory is an input to member composition, while transport and the
    invoker depend on the completed members. The seam therefore exposes the
    two decisions in that order so providers remain replaceable and a member
    is assembled exactly once.
    """

    def resolve_shared_memory(
        self,
        spec: TeamSpec,
        *,
        shared_layers: tuple[MemoryLayer, ...] = (),
    ) -> SharedMemoryStore | None: ...

    def build(
        self,
        spec: TeamSpec,
        *,
        members: tuple[AgentUnit, ...],
        shared_memory: SharedMemoryStore | None,
    ) -> object: ...


__all__ = [
    "TeamCommunication",
    "TeamCommunicationAssemblerProtocol",
    "TeamSeamFactoryProtocol",
    "TeamSharedMemoryResolverProtocol",
]
