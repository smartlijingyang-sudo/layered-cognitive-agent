"""Developer-facing API surface.

Import ``Agent`` and ``MultiAgentTeam`` from here (or from the package
root ``lca``). By default they share one lazily-constructed default
``Assembly()``; pass ``assembly=`` to isolate composition state.

Example::

    from lca import Agent, MultiAgentTeam

    researcher = Agent(role="Researcher", goal="Find info", backstory="...",
                       tools=[search_tool], llm=my_llm)
    team = MultiAgentTeam.pipeline(members=[researcher, writer])
    result = await team.run("Write a blog post about AI")
"""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.enums import MemoryLayer, TeamProcess
from lca.contracts.graph import ExecutionGraph
from lca.contracts.protocols import (
    Brain,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamProcessStrategy,
    TeamUnit,
    Tool,
)
from lca.contracts.result import Result
from lca.contracts.supervisor_mode import Recipe, SupervisorMode, expand_recipe
from lca.layer4_app.assembly import Assembly

_default_assembly: Assembly | None = None


def _get_default_assembly() -> Assembly:
    global _default_assembly
    if _default_assembly is None:
        _default_assembly = Assembly()
    return _default_assembly


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
        assembly: Assembly | None = None,
    ) -> None:
        target = assembly or _get_default_assembly()
        self._agent = target.assemble_agent(
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


class MultiAgentTeam:
    """A team of agents coordinated by a shared orchestration process.

    Prefer Recipe classmethods (``pipeline``, ``board``, ``manager``, …).
    Advanced: construct with ``process`` + optional ``supervisor_mode``.
    """

    def __init__(
        self,
        members: list[Agent],
        *,
        process: TeamProcess | None = None,
        recipe: Recipe | None = None,
        supervisor: Agent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[MemoryLayer] | None = None,
        execution_graph: ExecutionGraph | None = None,
        strategy: TeamProcessStrategy | None = None,
        supervisor_mode: SupervisorMode | None = None,
        delegate_max_attempts: int | None = None,
        assembly: Assembly | None = None,
    ) -> None:
        target = assembly or _get_default_assembly()
        base_members = [m._agent for m in members]
        base_supervisor = supervisor._agent if supervisor else None

        process_val = process
        mode = supervisor_mode
        if recipe is not None:
            process_val, recipe_mode = expand_recipe(recipe)
            if mode is None:
                mode = recipe_mode
        if process_val is None:
            process_val = TeamProcess.HIERARCHICAL

        self._orchestrator: TeamUnit = target.assemble_team(
            members=base_members,
            process=process_val,
            supervisor=base_supervisor,
            max_rounds=max_rounds,
            shared_memory_layers=shared_memory_layers,
            execution_graph=execution_graph,
            strategy=strategy,
            supervisor_mode=mode,
            delegate_max_attempts=delegate_max_attempts,
        )

    async def run(self, objective: str) -> Result:
        return await self._orchestrator.run(objective)

    @classmethod
    def pipeline(
        cls,
        members: list[Agent],
        **kwargs: object,
    ) -> MultiAgentTeam:
        return cls(members, recipe=Recipe.PIPELINE, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def fanout(cls, members: list[Agent], **kwargs: object) -> MultiAgentTeam:
        return cls(members, recipe=Recipe.FANOUT, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def manager(
        cls,
        supervisor: Agent,
        members: list[Agent],
        **kwargs: object,
    ) -> MultiAgentTeam:
        return cls(
            members,
            recipe=Recipe.MANAGER,
            supervisor=supervisor,
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def consult(
        cls,
        supervisor: Agent,
        members: list[Agent],
        **kwargs: object,
    ) -> MultiAgentTeam:
        return cls(
            members,
            recipe=Recipe.CONSULT,
            supervisor=supervisor,
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def board(
        cls,
        supervisor: Agent,
        members: list[Agent],
        **kwargs: object,
    ) -> MultiAgentTeam:
        return cls(
            members,
            recipe=Recipe.BOARD,
            supervisor=supervisor,
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def relay(cls, members: list[Agent], **kwargs: object) -> MultiAgentTeam:
        return cls(members, recipe=Recipe.RELAY, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def swarm(cls, members: list[Agent], **kwargs: object) -> MultiAgentTeam:
        return cls(members, recipe=Recipe.SWARM, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def debate(cls, members: list[Agent], **kwargs: object) -> MultiAgentTeam:
        return cls(members, recipe=Recipe.DEBATE, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def graph(
        cls,
        members: list[Agent],
        execution_graph: ExecutionGraph,
        **kwargs: object,
    ) -> MultiAgentTeam:
        return cls(
            members,
            recipe=Recipe.GRAPH,
            execution_graph=execution_graph,
            **kwargs,  # type: ignore[arg-type]
        )
