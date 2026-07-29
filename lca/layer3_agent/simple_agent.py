"""SimpleAgent —— 单个 Agent 的运行时封装。

L3 层职责：
    SimpleAgent 是 AgentEntrypoint 协议的默认实现，
    将 Runtime（认知闭环）+ RoleProfile（角色配置）组合为
    可调度的执行单元。支持 execute / resume / cancel 三种生命周期。
"""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.invocation import InvocationContext
from lca.contracts.mechanisms import Hook
from lca.contracts.message import AgentMessage, agent_message_as_text, agent_message_text
from lca.contracts.protocols import AgentEntrypoint, CompletionPolicy, Runtime
from lca.contracts.protocols.capabilities import HookRegistryHolder
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import StateSnapshot
from lca.contracts.team_progress import DelegationLedgerProtocol


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


class SimpleAgent(AgentEntrypoint):
    """单个 Agent 的运行时封装。

    持有 Runtime（认知闭环）和 RoleProfile（角色配置），
    提供 execute / resume / cancel 三种生命周期方法。
    """

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

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        """注册 Hook 到 Runtime 的 HookRegistry。"""
        runtime = self.runtime
        if isinstance(runtime, HookRegistryHolder):
            runtime.hooks.register(hook_name, hook_fn)

    def install_completion_guard(self, policy: CompletionPolicy) -> None:
        """通过 Runtime 协议安装确定性收尾 guardrail。"""
        self.runtime.install_completion_guard(policy)


# Transitional alias — remove after one release cycle (ADR-0021).
BaseAgent = SimpleAgent
