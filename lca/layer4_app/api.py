"""Developer-facing API surface.

Import ``Agent`` and ``MultiAgentTeam`` from here (or from the package
root ``lca``).  These are thin wrappers around the composition root
(``assembly``) that handle default registration and provide a clean,
minimal constructor signature.

Example::

    from lca import Agent, MultiAgentTeam
    from lca.contracts.enums import TeamProcess

    researcher = Agent(role="Researcher", goal="Find info", backstory="...",
                       tools=[search_tool], llm=my_llm)
    team = MultiAgentTeam(members=[researcher, writer], process=TeamProcess.SEQUENTIAL)
    result = await team.run("Write a blog post about AI")
"""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.enums import TeamProcess
from lca.contracts.protocols import (
    BrainStrategy,
    LLMAdapter,
    MemorySystem,
    Observability,
    OrchestrationStrategy,
    StateStore,
    TeamEntrypoint,
    Tool,
)
from lca.contracts.result import Result
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer4_app.assembly import assemble_base_agent, assemble_team
from lca.layer4_app.defaults import ensure_defaults

# Default wall-clock timeout for a single agent run (seconds).
DEFAULT_MAX_WALL_CLOCK_SECONDS: int = 300
# Minimum step budget when an Agent is promoted to team supervisor.
_SUPERVISOR_MIN_MAX_STEPS: int = 20


class Agent:
    """A single cognitive agent with role, goal, tools, and an LLM.

    Construct with a role description, a list of tools, and an LLM adapter.
    Call ``await agent.run(task)`` to execute a task through the cognitive
    runtime loop.

    Parameters
    ----------
    role:
        Short role label (e.g. ``"Researcher"``).
    goal:
        What this agent is trying to achieve.
    backstory:
        Narrative context that shapes the agent's behaviour.
    tools:
        Tools available to this agent.
    llm:
        The LLM adapter used for reasoning.
    max_steps:
        Maximum reasoning steps per ``run()`` call.
    max_wall_clock_seconds:
        Hard wall-clock timeout; ``None`` for no limit.
    memory:
        ``"simple"`` (default) or a ``MemorySystem`` instance.
    observability:
        ``"console"`` (default), ``"jsonl_file"``, or an ``Observability`` instance.
    state_store:
        ``"memory"`` (default) or a ``StateStore`` instance.
    brain_strategy:
        ``"default"`` or a registered strategy name / ``BrainStrategy`` instance.
    """

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
        brain_strategy: str | BrainStrategy = "default",
    ) -> None:
        ensure_defaults()
        self._base_agent = assemble_base_agent(
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
            brain_strategy=brain_strategy,
        )

    async def run(self, task: str) -> Result:
        """Execute *task* and return the result."""
        return await self._base_agent.execute(task)

    def _as_supervisor(self) -> BaseAgent:
        """Promote this agent to a team supervisor with a minimum step budget."""
        rp = self._base_agent.role_profile
        ms = self._base_agent.max_steps
        wc = self._base_agent.max_wall_clock_seconds
        return BaseAgent(
            self._base_agent.runtime,
            rp,
            max_steps=max(ms, _SUPERVISOR_MIN_MAX_STEPS),
            max_wall_clock_seconds=max(wc, DEFAULT_MAX_WALL_CLOCK_SECONDS)
            if wc
            else DEFAULT_MAX_WALL_CLOCK_SECONDS,
        )


class MultiAgentTeam:
    """A team of agents coordinated by a shared orchestration process.

    Parameters
    ----------
    members:
        The agents participating in this team.
    process:
        Orchestration pattern (hierarchical, sequential, parallel, etc.).
    supervisor:
        Optional supervisor agent (required for ``HIERARCHICAL`` process).
    max_rounds:
        Maximum coordination rounds; ``None`` for unlimited.
    shared_memory_layers:
        Memory layers shared across team members.
    graph_definition_ref:
        Reference to a graph definition (for ``GRAPH`` process).
    strategy:
        Optional custom ``OrchestrationStrategy`` override.
    """

    def __init__(
        self,
        members: list[Agent],
        process: TeamProcess = TeamProcess.HIERARCHICAL,
        supervisor: Agent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[str] | None = None,
        graph_definition_ref: str | None = None,
        strategy: OrchestrationStrategy | None = None,
    ) -> None:
        ensure_defaults()
        base_members = [m._base_agent for m in members]
        base_supervisor = supervisor._as_supervisor() if supervisor else None
        self._orchestrator: TeamEntrypoint = assemble_team(
            members=base_members,
            process=process,
            supervisor=base_supervisor,
            max_rounds=max_rounds,
            shared_memory_layers=shared_memory_layers,
            graph_definition_ref=graph_definition_ref,
            strategy=strategy,
        )

    async def run(self, objective: str) -> Result:
        """Run the team on *objective* and return the aggregated result."""
        return await self._orchestrator.run(objective)
