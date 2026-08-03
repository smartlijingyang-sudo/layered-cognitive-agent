"""Developer-facing API surface.

Import ``Agent``, ``Team``, ``TeamLead`` from here (or package root ``lca``).

Example::

    from lca import Agent, Team, TeamLead, Pipeline

    researcher = Agent(role="Researcher", goal="Find info", backstory="...",
                       tools=[], llm=my_llm)
    team = Team(members=[researcher, writer], coordination=Pipeline())
    result = await team.run("Write a blog post about AI")
"""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.enums import MemoryLayer
from lca.contracts.graph import ExecutionGraph
from lca.contracts.protocols import Brain, LLMAdapter, MemorySystem, Observability, StateStore, Tool
from lca.contracts.result import Result
from lca.contracts.team_coordination import (
    Coordination,
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.layer4_app.composer import AgentComposer, TeamComposer

_default_composer: TeamComposer | None = None


def _get_default_composer() -> TeamComposer:
    global _default_composer
    if _default_composer is None:
        _default_composer = TeamComposer()
    return _default_composer


class Agent:
    """A single cognitive agent with role, goal, tools, and an LLM."""

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: list[Tool],
        llm: LLMAdapter,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
        memory: str | MemorySystem = "simple",
        observability: str | Observability = "console",
        state_store: str | StateStore = "memory",
        brain: str | Brain = "default",
        composer: AgentComposer | None = None,
    ) -> None:
        target = composer or _get_default_composer()
        self._agent = target.compose(
            role=role,
            goal=goal,
            backstory=backstory,
            tools=tools,
            llm=llm,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
            memory=memory,
            observability=observability,
            state_store=state_store,
            brain=brain,
        )

    async def run(self, task: str) -> Result:
        return await self._agent.run(task)


class TeamLead:
    """Designated lead agent + mandate for a Team."""

    def __init__(self, agent: Agent, mandate: LeadMandate) -> None:
        self._cognitive = agent._agent
        self.mandate = mandate

    @classmethod
    def routing(cls, agent: Agent) -> TeamLead:
        return cls(agent, LeadMandate.ROUTING)

    @classmethod
    def consult(cls, agent: Agent) -> TeamLead:
        return cls(agent, LeadMandate.CONSULT)

    @classmethod
    def board(cls, agent: Agent) -> TeamLead:
        return cls(agent, LeadMandate.BOARD)


class Team:
    """A team of agents: members + exactly one of lead or coordination."""

    def __init__(
        self,
        members: list[Agent],
        *,
        lead: TeamLead | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: list[MemoryLayer] | None = None,
        delegate_max_attempts: int | None = None,
        composer: TeamComposer | None = None,
    ) -> None:
        if (lead is None) == (coordination is None):
            raise ValueError("Team requires exactly one of lead= or coordination=")

        target = composer or _get_default_composer()
        base_members = [m._agent for m in members]
        lead_arg = (lead._cognitive, lead.mandate) if lead is not None else None

        self._orchestrator = target.compose_team(
            members=base_members,
            lead=lead_arg,
            coordination=coordination,
            shared_memory_layers=shared_memory_layers,
            delegate_max_attempts=delegate_max_attempts,
        )

    async def run(self, objective: str) -> Result:
        return await self._orchestrator.run(objective)

    @classmethod
    def pipeline(cls, members: list[Agent], **kwargs: object) -> Team:
        return cls(members, coordination=Pipeline(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def fan_out(cls, members: list[Agent], **kwargs: object) -> Team:
        return cls(members, coordination=FanOut(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def peer_relay(cls, members: list[Agent], **kwargs: object) -> Team:
        return cls(members, coordination=PeerRelay(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def peer_swarm(
        cls,
        members: list[Agent],
        *,
        max_rounds: int = 3,
        **kwargs: object,
    ) -> Team:
        return cls(members, coordination=PeerSwarm(max_rounds=max_rounds), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def debate(
        cls,
        members: list[Agent],
        *,
        max_rounds: int = 3,
        **kwargs: object,
    ) -> Team:
        return cls(members, coordination=Debate(max_rounds=max_rounds), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def graph(
        cls,
        members: list[Agent],
        execution_graph: ExecutionGraph,
        **kwargs: object,
    ) -> Team:
        return cls(
            members,
            coordination=Graph(execution_graph=execution_graph),
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def with_lead(
        cls,
        lead: TeamLead,
        members: list[Agent],
        **kwargs: object,
    ) -> Team:
        return cls(members, lead=lead, **kwargs)  # type: ignore[arg-type]
