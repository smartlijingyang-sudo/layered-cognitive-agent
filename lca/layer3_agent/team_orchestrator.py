"""TeamOrchestrator — team shape, channel, and process strategy."""

from __future__ import annotations

from lca.contracts.enums import ComponentKind, DecisionGateName, RoleMode
from lca.contracts.member_status import MemberStatus
from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import (
    AgentTransport,
    SharedMemoryStore,
    TeamContext,
    TeamProcessStrategy,
    TeamUnit,
)
from lca.contracts.protocols.capabilities import (
    HasBrainBodyMemory,
    HasChannel,
    HasSharedMemory,
)
from lca.contracts.protocols.cognition import DecisionGate, SupportsDecisionGate
from lca.contracts.registries import Registries
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.simple_agent import CognitiveAgent


class TeamOrchestrator(TeamUnit):
    """Resolve process strategy, inject shared memory, bind supervisor setup."""

    def __init__(
        self,
        members: list[CognitiveAgent],
        config: TeamConfig,
        *,
        registries: Registries,
        supervisor: CognitiveAgent | None = None,
        transport: AgentTransport | None = None,
        teammates: list[RoleProfile] | None = None,
        role_mode: RoleMode = RoleMode.SOLO,
        strategy: TeamProcessStrategy | None = None,
        team_id: str = "",
    ) -> None:
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.teammates = teammates or []
        self.role_mode = role_mode
        self.team_id = team_id or f"team-{config.process}"

        if strategy is not None:
            self._strategy = strategy
        else:
            self._strategy = registries.orchestration.resolve(config.process)

        self._shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            self._shared_store = TeamSharedMemoryStore(config.shared_memory_layers)
            self._inject_shared_memory()

        member_status: MemberStatus | None = None
        if supervisor is not None:
            member_status = self._create_member_status(members, registries)
            policy = self._resolve_decision_gate(config, registries)
            self._bind_supervisor(supervisor, transport, policy)

        self._context = TeamContext(
            members=members,
            config=config,
            supervisor=supervisor,
            transport=transport,
            teammates=self.teammates,
            role_mode=self.role_mode,
            member_status=member_status,
        )

    @staticmethod
    def _create_member_status(
        members: list[CognitiveAgent], registries: Registries
    ) -> MemberStatus:
        required_roles = frozenset(m.role_profile.role for m in members)
        cls = registries.components.require(ComponentKind.MEMBER_STATUS, "default")
        result = cls(required_roles=required_roles)
        if not isinstance(result, MemberStatus):
            raise TypeError(
                f"member_status factory produced {type(result).__name__}, expected MemberStatus"
            )
        return result

    @staticmethod
    def _resolve_decision_gate(config: TeamConfig, registries: Registries) -> DecisionGate | None:
        policy_name = config.decision_gate if config else DecisionGateName.MUST_CONSULT_ALL
        if policy_name == DecisionGateName.NONE:
            return None
        factory = registries.components.require(ComponentKind.DECISION_GATE, policy_name)
        result = factory()
        if not isinstance(result, DecisionGate):
            raise TypeError(
                f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
            )
        return result

    def _inject_shared_memory(self) -> None:
        if self._shared_store is None:
            return
        for member in self.members:
            if isinstance(member.runtime, HasBrainBodyMemory):
                memory = member.runtime.memory
                if isinstance(memory, HasSharedMemory):
                    memory.bind_shared_memory(self._shared_store)

    @staticmethod
    def _bind_supervisor(
        supervisor: CognitiveAgent,
        transport: AgentTransport | None,
        policy: DecisionGate | None,
    ) -> None:
        """Bind supervisor capabilities at composition time.

        Wires channel and decision gate — the bindings that make an
        agent act as a hierarchical supervisor. Teammates text flows
        through RunContext → AgentState at run time, not here.
        """
        rt = supervisor.runtime
        if not isinstance(rt, HasBrainBodyMemory):
            return
        if transport is not None and isinstance(rt.body, HasChannel):
            rt.body.bind_channel(transport)
        if policy is not None and isinstance(rt.brain, SupportsDecisionGate):
            rt.brain.install_decision_gate(policy)

    async def run(self, objective: str | object) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
