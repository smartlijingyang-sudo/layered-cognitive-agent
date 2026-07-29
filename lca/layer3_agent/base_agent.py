"""BaseAgent —— 持有 Runtime + Brain + Body + Memory 视图。"""

from __future__ import annotations

from lca.contracts.invocation import InvocationContext
from lca.contracts.message import AgentMessage, agent_message_as_text, agent_message_text
from lca.contracts.protocols import AgentEntrypoint, Runtime
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import StateSnapshot
from lca.contracts.team_progress import DelegationLedgerProtocol


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


class BaseAgent(AgentEntrypoint):
    """单个 Agent 的运行时封装。"""

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        max_steps: int = 10,
        max_wall_clock_seconds: int | None = None,
    ):
        self.runtime = runtime
        self.role_profile = role_profile
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds

    async def execute(
        self,
        task: str | AgentMessage,
        ctx: InvocationContext | None = None,
        team_progress: DelegationLedgerProtocol | None = None,
        **context: str,
    ) -> Result:
        text = _task_as_text(task)
        if ctx is not None:
            if ctx.delegated_by:
                context.setdefault("delegated_by", ctx.delegated_by)
            if ctx.trace_id:
                context.setdefault("trace_id", ctx.trace_id)
        return await self.runtime.run(
            text,
            max_steps=self.max_steps,
            max_wall_clock_seconds=self.max_wall_clock_seconds,
            team_progress=team_progress,
            agent_role=self.role_profile.role,
            **context,
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
        """尽力取消；默认 Runtime 无全局 cancel 时为 no-op。"""
        return None
