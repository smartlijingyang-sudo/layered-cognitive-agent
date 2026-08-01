"""Agent — Worker 的单认知体实现。

委派认知循环给 CognitiveEngine（重构后的概念，
替代现有 CognitiveRuntime + Brain + Body + MemorySystem 四件套）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from layer_top.contracts import Task, Worker
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import Budget


@runtime_checkable
class CognitiveEngine(Protocol):
    """认知引擎 — 接收 Task + 身份，运行 think→act→observe 循环，返回产出。

    Agent 只负责 Task→Result 映射，认知循环的内部结构
    （推理、工具执行、状态跟踪）是引擎的下一层职责。
    """

    async def run(self, task: Task, identity: RoleProfile) -> str: ...


class Agent(Worker):
    """单认知体 — Worker 协议实现，委派认知循环给 CognitiveEngine。"""

    def __init__(self, identity: RoleProfile, engine: CognitiveEngine) -> None:
        self._identity = identity
        self._engine = engine

    async def execute(self, task: Task) -> Result:
        output = await self._engine.run(task, self._identity)
        return Result(
            trace_id="",
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=0,
            budget_used=Budget(),
            output=output,
        )
