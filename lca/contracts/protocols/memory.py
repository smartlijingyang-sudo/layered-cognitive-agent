"""L1 Memory 协议。

SharedMemoryStore 定义在 orchestration.py（团队级共享状态），
本文件只定义单体会话内的 MemorySystem。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState


@runtime_checkable
class MemorySystem(Protocol):
    """记忆系统：检索感知 + 多级写入 + 显式查询。

    三阶段语义：
    - perceive：think 之前，返回携带检索上下文的新 ``AgentState`` 值，不修改传入实例
    - update：reflect 之后，写入 observation + reflection（ADR-0066 计划拆
      为 propose + commit；本 PR 仅集中 reducer 调用入口，拆 deferred）
    - query：显式检索指定层的记录（共享记忆统一入口）
    """

    async def perceive(self, state: AgentState) -> AgentState: ...

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None: ...

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]: ...


@runtime_checkable
class RetrievalPolicy(Protocol):
    """按 4 层语义从记忆存储挑选记录到 ``retrieved_context``（ADR-0068）。

    默认实现 ``NullRetrievalPolicy`` 不选任何 record（宪法 §3.4 默认 no-op）；
    标准 bundle 装 ``LayeredRetrievalPolicy``：working 永保留，semantic/procedural
    按 recency 共享 70% budget，episodic 仅余量填充 30%。
    """

    def retrieve(
        self,
        layers: dict[MemoryLayer, list[MemoryRecord]],
        budget: int,
    ) -> list[MemoryRecord]: ...
