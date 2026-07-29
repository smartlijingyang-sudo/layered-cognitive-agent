"""L4 极简开发者 API。"""

from __future__ import annotations

from lca.contracts.enums import TeamProcess
from lca.contracts.protocols import (
    BrainStrategy,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamEntrypoint,
    Tool,
)
from lca.contracts.result import Result
from lca.layer3_agent.supervisor import Supervisor
from lca.layer4_app.assembly import assemble_base_agent, assemble_team
from lca.layer4_app.defaults import ensure_defaults


class Agent:
    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: list[Tool],
        llm: LLMAdapter,
        max_steps: int = 10,
        max_wall_clock_seconds: int | None = 300,
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
        return await self._base_agent.execute(task)

    def _as_supervisor(self) -> Supervisor:
        rp = self._base_agent.role_profile
        ms = self._base_agent.max_steps
        wc = self._base_agent.max_wall_clock_seconds
        return Supervisor(
            self._base_agent.runtime,
            rp,
            max_steps=max(ms, 20),
            max_wall_clock_seconds=max(wc, 300) if wc else 300,
        )


class MultiAgentTeam:
    def __init__(
        self,
        members: list[Agent],
        process: TeamProcess = TeamProcess.HIERARCHICAL,
        supervisor: Agent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[str] | None = None,
        graph_definition_ref: str | None = None,
        strategy: object | None = None,
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
        return await self._orchestrator.run(objective)
