"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.mechanisms import Hook
from lca.contracts.message import AgentMessage, agent_message_as_text, agent_message_text
from lca.contracts.protocols import AgentUnit, Runtime
from lca.contracts.protocols.capabilities import HasHooks
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.run_context import RunContext
from lca.contracts.state import StateSnapshot


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


class CognitiveAgent(AgentUnit):
    """Runtime + RoleProfile as a schedulable unit with run / resume / cancel."""

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
    ) -> None:
        self.runtime = runtime
        self.role_profile = role_profile
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result:
        text = _task_as_text(task)
        return await self.runtime.run(
            text,
            ctx,
            max_steps=self.max_steps,
            max_wall_clock_seconds=self.max_wall_clock_seconds,
            agent_role=self.role_profile.role,
        )

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: str | AgentMessage | None = None,
    ) -> Result:
        msg = None
        if isinstance(input, AgentMessage):
            msg = input
        elif isinstance(input, str):
            msg = agent_message_text(input)
        return await self.runtime.resume(snapshot, input=msg, max_steps=self.max_steps)

    async def cancel(self) -> None:
        return None

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        runtime = self.runtime
        if isinstance(runtime, HasHooks):
            runtime.hooks.register(hook_name, hook_fn)
