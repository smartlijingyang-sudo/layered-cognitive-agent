"""L3 Agent 级入口协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.result import Result


@runtime_checkable
class AgentRuntime(Protocol):
    async def execute(self, task: str, **context: str) -> Result: ...


@runtime_checkable
class TeamRuntime(Protocol):
    """团队级入口契约：接收 objective，跑完编排后返回 Result。

    区别于 AgentRuntime.execute：语义单位是"团队"而非单个 Agent，
    不携带 max_steps（预算下沉到各 BaseAgent 自身）。
    """

    async def run(self, objective: str) -> Result: ...
