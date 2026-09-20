"""L1 Memory 与时态存储协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord, MemoryRelationKind
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState


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

    async def retrieve(self, manifest: ContextManifest) -> list[MemoryRecord]:
        """Retrieve context-relevant memories for the current turn (ADR-0244 D4).

        Called by ``phase.perceive.memory_retrieve``; must return typed
        ``MemoryRecord`` values and never raise on empty memory.
        """


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
class MemoryStore(Protocol):
    """结构化记忆仓储（ADR-0246）：typed 记录的幂等写入与 supersede 生命周期。

    ``upsert`` 按 ``dedupe_key`` 幂等：同一 ``dedupe_key`` 的新事实通过
    ``supersede`` 退役旧记录并建立 ``revision_of`` 血缘。``query`` 可按
    ``category`` 过滤，默认排除已 superseded / 过期记录。实现必须保证
    写入幂等、可审计，且不绕过 ``Session`` 事实流（记忆面 SSOT 在
    ``{home}/memory/``，ADR-0242）。
    """

    def upsert(self, record: MemoryRecord) -> MemoryRecord: ...

    def supersede(
        self,
        record_id: str,
        replacement: MemoryRecord,
        *,
        reason: str = "superseded",
    ) -> MemoryRecord: ...

    def query(
        self,
        *,
        category: MemoryCategory | None = None,
        include_superseded: bool = False,
        limit: int = 50,
    ) -> list[MemoryRecord]: ...


@runtime_checkable
class MemoryTool(Protocol):
    """受治理记忆工具族契约（ADR-0246）。

    模型通过 ``memory_search`` / ``memory_add`` / ``memory_update`` /
    ``memory_remove`` 读写结构化记忆。所有写操作必须走 C10 窄门
    （``CommandEnvelope`` + ``effect_gateway``），capability 为
    ``memory.read``（读）与 ``memory.update``（写）；读操作返回 typed
    ``MemoryRecord``，写操作返回幂等回执。
    """

    name: str
    description: str

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]: ...

    def add(self, record: MemoryRecord) -> MemoryRecord: ...

    def update(self, record_id: str, record: MemoryRecord) -> MemoryRecord: ...

    def remove(self, record_id: str) -> None: ...


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


__all__ = [
    "MemoryStore",
    "MemorySystem",
    "MemoryTool",
    "RetrievalPolicy",
    "TemporalMemoryStore",
]
