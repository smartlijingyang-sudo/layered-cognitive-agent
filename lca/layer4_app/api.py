"""Developer-facing API surface.

Import ``Agent`` and ``MultiAgentTeam`` from here (or from the package
root ``lca``). By default they share one lazily-constructed default
``Assembly()``; pass ``assembly=`` to isolate composition state (custom
registered implementations, test isolation).

Example::

    from lca import Agent, MultiAgentTeam
    from lca.contracts.enums import TeamProcess

    researcher = Agent(role="Researcher", goal="Find info", backstory="...",
                       tools=[search_tool], llm=my_llm)
    team = MultiAgentTeam(members=[researcher, writer], process=TeamProcess.SEQUENTIAL)
    result = await team.run("Write a blog post about AI")
"""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.enums import DecisionGateName, MemoryLayer, TeamProcess
from lca.contracts.graph import ExecutionGraph
from lca.contracts.orchestration_taxonomy import SupervisorPlane
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
from lca.layer4_app.assembly import Assembly

_default_assembly: Assembly | None = None


def _get_default_assembly() -> Assembly:
    global _default_assembly
    if _default_assembly is None:
        _default_assembly = Assembly()
    return _default_assembly


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
    brain:
        ``"default"`` or a registered brain factory name / ``Brain`` instance.
    assembly:
        Optional. Pass your own ``Assembly`` to isolate composition state
        (e.g. custom registered implementations, or test isolation); when
        omitted, the process-default lazily-constructed Assembly is used.
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
        """Execute *task* and return the result."""
        return await self._agent.run(task)


class MultiAgentTeam:
    """A team of agents coordinated by a shared orchestration process.

    Parameters
    ----------
    members:
        The agents participating in this team.
    process:
        Topology within an orchestration family (see ADR-0027).
    supervisor:
        Optional supervisor agent (required for ``HIERARCHICAL`` process).
    max_rounds:
        Maximum coordination rounds; ``None`` for unlimited.
    shared_memory_layers:
        Memory layers shared across team members.
    execution_graph:
        Required when ``process=GRAPH`` (unless a custom *strategy* is passed).
    strategy:
        Optional custom ``TeamProcessStrategy`` override.
    decision_gate:
        SUPERVISOR settlement strength. Default ``none`` (free supervisor).
        Use ``must_consult_all`` for full consultation compliance.
    supervisor_plane:
        SUPERVISOR control-plane kind: ``consultation`` (settlement board)
        or ``routing`` (free PM). Illegal with non-none gate under routing.
    delegate_max_attempts:
        Per-role delegate retries on the consultation board.
    assembly:
        Optional. Pass your own ``Assembly`` to isolate composition state;
        when omitted, the process-default lazily-constructed Assembly is used.
    """

    def __init__(
        self,
        members: list[Agent],
        process: TeamProcess = TeamProcess.HIERARCHICAL,
        supervisor: Agent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[MemoryLayer] | None = None,
        execution_graph: ExecutionGraph | None = None,
        strategy: TeamProcessStrategy | None = None,
        decision_gate: DecisionGateName | None = None,
        supervisor_plane: SupervisorPlane | None = None,
        delegate_max_attempts: int | None = None,
        assembly: Assembly | None = None,
    ) -> None:
        target = assembly or _get_default_assembly()
        base_members = [m._agent for m in members]
        base_supervisor = supervisor._agent if supervisor else None
        self._orchestrator: TeamUnit = target.assemble_team(
            members=base_members,
            process=process,
            supervisor=base_supervisor,
            max_rounds=max_rounds,
            shared_memory_layers=shared_memory_layers,
            execution_graph=execution_graph,
            strategy=strategy,
            decision_gate=decision_gate,
            supervisor_plane=supervisor_plane,
            delegate_max_attempts=delegate_max_attempts,
        )

    async def run(self, objective: str) -> Result:
        """Run the team on *objective* and return the aggregated result."""
        return await self._orchestrator.run(objective)
