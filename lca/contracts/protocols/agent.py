"""L3 Agent 级入口协议。
agent.py 的极简是刻意的克制——L3 门面协议不应该关心"怎么想"，只关心"怎么进/怎么出"
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.invocation import InvocationContext
from lca.contracts.message import AgentMessage
from lca.contracts.result import Result
from lca.contracts.state import StateSnapshot


@runtime_checkable
class AgentRuntime(Protocol):
    async def execute(
        self, task: str | AgentMessage, ctx: InvocationContext | None = None
    ) -> Result: ...
    async def resume(
        self, snapshot: StateSnapshot, input: str | AgentMessage | None = None
    ) -> Result: ...
    async def cancel(self) -> None: ...


@runtime_checkable
class TeamRuntime(Protocol):
    """团队级入口契约：接收 objective，跑完编排后返回 Result。

    区别于 AgentRuntime.execute：语义单位是"团队"而非单个 Agent，
    不携带 max_steps（预算下沉到各 BaseAgent 自身）。
    """

    async def run(
        self, objective: str | AgentMessage, ctx: InvocationContext | None = None
    ) -> Result: ...
