"""MultiAgent — Worker 的多认知体实现。

委派编排逻辑给 OrchestrationStrategy（重构后的概念，
替代现有 TeamProcessStrategy + TeamContext + SharedMemoryStore 碎片）。
成员类型是 list[Worker]，支持递归嵌套。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from layer_top.contracts import Task, Worker
from lca.contracts.result import Result


@runtime_checkable
class OrchestrationStrategy(Protocol):
    """编排策略 — 接收 Task + 成员，决定分发方式，返回 Result。

    分发方式（顺序/并行/层级/图）是策略的内部实现，
    MultiAgent 不关心具体怎么编排。
    """

    async def orchestrate(self, task: Task, members: list[Worker]) -> Result: ...


class MultiAgent(Worker):
    """多认知体 — Worker 协议实现，委派编排给 OrchestrationStrategy。

    成员类型是 list[Worker]，所以成员可以是 Agent 也可以是另一个 MultiAgent，
    天然递归嵌套。
    """

    def __init__(
        self, members: list[Worker], strategy: OrchestrationStrategy
    ) -> None:
        self._members = members
        self._strategy = strategy

    async def execute(self, task: Task) -> Result:
        return await self._strategy.orchestrate(task, self._members)
