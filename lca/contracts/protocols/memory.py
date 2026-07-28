"""L1 Memory 协议。

SharedMemoryStore 定义在 orchestration.py（团队级共享状态），
本文件只定义单体会话内的 MemorySystem。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.decision import Observation, Reflection
from lca.contracts.state import TypedState


@runtime_checkable
class MemorySystem(Protocol):
    """记忆系统：检索感知 + 多级写入。

    两阶段语义（ADR-0016）：
    - perceive / perceive_and_retrieve：think 之前，刷新 retrieved_context
    - update / update_multi_level：reflect 之后，写入 observation + reflection
    """

    async def perceive_and_retrieve(self, state: TypedState) -> TypedState: ...

    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None: ...

    async def perceive(self, state: TypedState) -> TypedState:
        """perceive_and_retrieve 的语义别名（两阶段 API）。"""
        return await self.perceive_and_retrieve(state)

    async def update(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None:
        """update_multi_level 的语义别名（两阶段 API）。"""
        await self.update_multi_level(state, observation, reflection)
