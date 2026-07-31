"""L1 Memory 协议。

SharedMemoryStore 定义在 orchestration.py（团队级共享状态），
本文件只定义单体会话内的 MemorySystem。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.decision import Observation, Reflection
from lca.contracts.memory import MemoryRecord
from lca.contracts.state import AgentState


@runtime_checkable
class MemorySystem(Protocol):
    """记忆系统：检索感知 + 多级写入 + 显式查询。

    两阶段语义（ADR-0016）：
    - perceive：think 之前，刷新 retrieved_context
    - update：reflect 之后，写入 observation + reflection
    - query：显式检索指定层的记录（共享记忆统一入口）
    """

    async def perceive(self, state: AgentState) -> AgentState: ...

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None: ...

    def query(self, layer: str) -> list[MemoryRecord]: ...
