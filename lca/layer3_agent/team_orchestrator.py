"""TeamOrchestrator — team shape, channel, and process strategy."""

from __future__ import annotations

from typing import cast

from lca.contracts.enums import DecisionGateName
from lca.contracts.member_status import MemberStatus
from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import (
    AgentTransport,
    SharedMemoryStore,
    TeamContext,
    TeamProcessStrategy,
    TeamUnit,
)
from lca.contracts.protocols.capabilities import HasBrainBodyMemory, HasSharedMemory
from lca.contracts.protocols.cognition import DecisionGate
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.layer0_infra.component_registry import get_global_registry
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.simple_agent import CognitiveAgent
from lca.layer3_agent.supervisor_role import SupervisorSetup, apply_supervisor_setup


class TeamOrchestrator(TeamUnit):
    """Resolve process strategy, inject shared memory, bind supervisor setup."""

    def __init__(
        self,
        members: list[CognitiveAgent],
        config: TeamConfig,
        supervisor: CognitiveAgent | None = None,
        transport: AgentTransport | None = None,
        teammates_text: str = "",
        strategy: TeamProcessStrategy | None = None,
        team_id: str = "",
    ) -> None:
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.teammates_text = teammates_text
        self.team_id = team_id or f"team-{config.process}"

        if strategy is not None:
            self._strategy = strategy
        else:
            registry = get_global_orchestration_registry()
            self._strategy = registry.resolve(config.process)

        self._shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            self._shared_store = TeamSharedMemoryStore(config.shared_memory_layers)
            self._inject_shared_memory()

        member_status: MemberStatus | None = None
        if supervisor is not None:
            member_status = self._create_member_status(members)
            policy = self._resolve_decision_gate(config)
            setup = SupervisorSetup(
                channel=transport,
                teammates_text=teammates_text,
                member_status=member_status,
                decision_gate=policy,
            )
            apply_supervisor_setup(supervisor, setup)

        self._context = TeamContext(
            members=members,
            config=config,
            supervisor=supervisor,
            transport=transport,
            teammates_text=teammates_text,
            member_status=member_status,
            team_id=self.team_id,
            shared_memory=self._shared_store,
        )

    @staticmethod
    def _create_member_status(members: list[CognitiveAgent]) -> MemberStatus:
        required_roles = frozenset(m.role_profile.role for m in members)
        reg = get_global_registry()
        cls = reg.require("member_status", "default")
        return cast("MemberStatus", cls(required_roles=required_roles))

    @staticmethod
    def _resolve_decision_gate(config: TeamConfig) -> DecisionGate | None:
        policy_name = config.decision_gate if config else DecisionGateName.MUST_CONSULT_ALL
        if policy_name == DecisionGateName.NONE:
            return None
        reg = get_global_registry()
        factory = reg.require("decision_gate", policy_name)
        return cast("DecisionGate", factory())

    def _inject_shared_memory(self) -> None:
        if self._shared_store is None:
            return
        for member in self.members:
            if isinstance(member.runtime, HasBrainBodyMemory):
                memory = member.runtime.memory
                if isinstance(memory, HasSharedMemory):
                    memory.bind_shared_memory(self._shared_store)

    async def run(self, objective: str | object) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
