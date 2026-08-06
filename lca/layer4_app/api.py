"""Developer-facing API surface（ADR-0030 公共面 + ADR-0033 spec 化）。

Import ``Agent``, ``Team``, ``TeamLead`` from here (or package root ``lca``).
门面是声明式 spec 的持有者 + 符合 contracts 协议的入口：``Agent`` 满足
``AgentUnit``、``Team`` 满足 ``TeamUnit``；组装委托给各自持有的 composer
（显式可注入，无进程级全局单例）。

Example::

    from lca import Agent, Team, TeamLead, Pipeline

    researcher = Agent(role="Researcher", goal="Find info", backstory="...",
                       tools=[], llm=my_llm)
    team = Team(members=[researcher, writer], coordination=Pipeline())
    result = await team.run("Write a blog post about AI")
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.models.core.message import AgentMessage
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.team.graph import ExecutionGraph
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.models.team.team_coordination import (
    DEFAULT_COORDINATION_MAX_ROUNDS,
    Coordination,
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.contracts.protocols import (
    AgentUnit,
    Brain,
    LLMAdapter,
    MemorySystem,
    ObservabilityBackend,
    StateStore,
    TeamUnit,
    Tool,
)
from lca.contracts.protocols.spec import (
    BRAIN_CHOICE_DEFAULT,
    DEFAULT_DELEGATE_MAX_ATTEMPTS,
    MEMORY_CHOICE_SIMPLE,
    OBSERVABILITY_CHOICE_CONSOLE,
    STATE_STORE_CHOICE_MEMORY,
    AgentSpec,
    Governance,
    LeadSpec,
    TeamSpec,
)
from lca.layer4_app.composer import AgentComposer, TeamComposer


class Agent(AgentUnit):
    """A single cognitive agent：声明式构造规格 + 由它组装的封闭对象图。"""

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: Sequence[Tool],
        llm: LLMAdapter,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
        memory: str | MemorySystem = MEMORY_CHOICE_SIMPLE,
        observability: str | ObservabilityBackend = OBSERVABILITY_CHOICE_CONSOLE,
        state_store: str | StateStore = STATE_STORE_CHOICE_MEMORY,
        brain: str | Brain = BRAIN_CHOICE_DEFAULT,
        composer: AgentComposer | None = None,
    ) -> None:
        self._spec = AgentSpec(
            profile=RoleProfile(
                role=role,
                goal=goal,
                backstory=backstory,
                tool_permission_manifest=ToolPermissionManifest(
                    allowed_tools=[t.name for t in tools]
                ),
            ),
            llm=llm,
            tools=tuple(tools),
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
            memory=memory,
            observability=observability,
            state_store=state_store,
            brain=brain,
        )
        target = composer if composer is not None else AgentComposer()
        self._agent = target.compose(self._spec)
        self.role_profile = self._spec.profile

    @property
    def spec(self) -> AgentSpec:
        """声明式构造规格 —— 团队重组的唯一事实来源。"""
        return self._spec

    async def run(self, task: str | AgentMessage, ctx: RunContext | None = None) -> Result:
        return await self._agent.run(task, ctx)

    async def resume(
        self, snapshot: StateSnapshot, input: str | AgentMessage | None = None
    ) -> Result:
        return await self._agent.resume(snapshot, input)

    async def cancel(self) -> None:
        await self._agent.cancel()


class TeamLead:
    """Designated lead agent + mandate：LeadSpec 的门面持有者。"""

    def __init__(self, agent: Agent, mandate: LeadMandate) -> None:
        self._spec = LeadSpec(agent=agent.spec, mandate=mandate)

    @property
    def spec(self) -> LeadSpec:
        return self._spec

    @property
    def mandate(self) -> LeadMandate:
        return self._spec.mandate

    @classmethod
    def routing(cls, agent: Agent) -> TeamLead:
        return cls(agent, LeadMandate.ROUTING)

    @classmethod
    def consult(cls, agent: Agent) -> TeamLead:
        return cls(agent, LeadMandate.CONSULT)

    @classmethod
    def board(cls, agent: Agent) -> TeamLead:
        return cls(agent, LeadMandate.BOARD)


class Team(TeamUnit):
    """A team of agents: members + exactly one of lead or coordination."""

    def __init__(
        self,
        members: Sequence[Agent],
        *,
        lead: TeamLead | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: Sequence[MemoryLayer] | None = None,
        delegate_max_attempts: int | None = None,
        observability: str | ObservabilityBackend | None = None,
        composer: TeamComposer | None = None,
    ) -> None:
        governance: Governance
        if lead is not None:
            if coordination is not None:
                raise ValueError("Team requires exactly one of lead= or coordination=")
            governance = lead.spec
        elif coordination is not None:
            governance = coordination
        else:
            raise ValueError("Team requires exactly one of lead= or coordination=")
        self._spec = TeamSpec(
            members=tuple(member.spec for member in members),
            governance=governance,
            shared_memory_layers=tuple(shared_memory_layers or ()),
            delegate_max_attempts=(
                delegate_max_attempts
                if delegate_max_attempts is not None
                else DEFAULT_DELEGATE_MAX_ATTEMPTS
            ),
            observability=observability,
        )
        target = composer if composer is not None else TeamComposer()
        self._handle = target.compose_team_spec(self._spec)

    @property
    def spec(self) -> TeamSpec:
        """声明式构造规格 —— 团队重组的唯一事实来源。"""
        return self._spec

    async def run(self, objective: str | AgentMessage) -> Result:
        return await self._handle.run(objective)

    @classmethod
    def pipeline(cls, members: Sequence[Agent], **kwargs: Any) -> Team:
        return cls(members, coordination=Pipeline(), **kwargs)

    @classmethod
    def fan_out(cls, members: Sequence[Agent], **kwargs: Any) -> Team:
        return cls(members, coordination=FanOut(), **kwargs)

    @classmethod
    def peer_relay(cls, members: Sequence[Agent], **kwargs: Any) -> Team:
        return cls(members, coordination=PeerRelay(), **kwargs)

    @classmethod
    def peer_swarm(
        cls,
        members: Sequence[Agent],
        *,
        max_rounds: int = DEFAULT_COORDINATION_MAX_ROUNDS,
        **kwargs: Any,
    ) -> Team:
        return cls(members, coordination=PeerSwarm(max_rounds=max_rounds), **kwargs)

    @classmethod
    def debate(
        cls,
        members: Sequence[Agent],
        *,
        max_rounds: int = DEFAULT_COORDINATION_MAX_ROUNDS,
        **kwargs: Any,
    ) -> Team:
        return cls(members, coordination=Debate(max_rounds=max_rounds), **kwargs)

    @classmethod
    def graph(
        cls,
        members: Sequence[Agent],
        execution_graph: ExecutionGraph,
        **kwargs: Any,
    ) -> Team:
        return cls(members, coordination=Graph(execution_graph=execution_graph), **kwargs)

    @classmethod
    def with_lead(cls, lead: TeamLead, members: Sequence[Agent], **kwargs: Any) -> Team:
        return cls(members, lead=lead, **kwargs)
