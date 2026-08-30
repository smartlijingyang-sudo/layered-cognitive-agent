"""L1 Memory 与时态存储协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord, MemoryRelationKind
from lca.contracts.models.core.state import AgentState


@runtime_checkable
class MemorySystem(Protocol):
    """记忆系统：检索感知 + 多级写入 + 显式查询。

    三阶段语义：
    - perceive：think 之前，返回携带检索上下文的新 ``AgentState`` 值，不修改传入实例
    - update：reflect 之后，写入 observation + reflection
    - query：显式检索指定层的记录（共享记忆统一入口）
    """

    async def perceive(self, state: AgentState) -> AgentState: ...

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None: ...

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]: ...


@runtime_checkable
class TemporalMemoryStore(Protocol):
    """时态事实的持久化边界。

    写入是追加式；修订和退役只改变历史记录的有效区间，并建立可追溯关系。
    ``recall`` 必须按 scope 和可选 ``as_of_ms`` 过滤，返回的结果只可作为数据证据。
    """

    def remember(self, record: MemoryRecord) -> MemoryRecord: ...

    def revise(
        self,
        record_id: str,
        replacement: MemoryRecord,
        *,
        reason: str = "revised",
    ) -> MemoryRecord: ...

    def retire(
        self, record_id: str, *, reason: str = "retired", at_ms: int | None = None
    ) -> None: ...

    def relate(
        self,
        source_id: str,
        target_id: str,
        relation: MemoryRelationKind,
        *,
        created_at_ms: int | None = None,
    ) -> None: ...

    def recall(
        self,
        *,
        scope_id: str,
        query: str,
        as_of_ms: int | None = None,
        limit: int = 8,
    ) -> list[MemoryRecord]: ...

    def list_records(
        self, *, scope_id: str, include_retired: bool = False
    ) -> list[MemoryRecord]: ...

    def close(self) -> None: ...


@runtime_checkable
class RetrievalPolicy(Protocol):
    """按 4 层语义从记忆存储挑选记录到 ``retrieved_context``（ADR-0068）。

    默认实现 ``NullRetrievalPolicy`` 不选任何 record；标准 bundle 装
    ``LayeredRetrievalPolicy``：working 永保留，semantic/procedural 按 recency
    共享 70% budget，episodic 仅余量填充 30%。
    """

    def retrieve(
        self,
        layers: dict[MemoryLayer, list[MemoryRecord]],
        budget: int,
    ) -> list[MemoryRecord]: ...


__all__ = ["MemorySystem", "RetrievalPolicy", "TemporalMemoryStore"]
