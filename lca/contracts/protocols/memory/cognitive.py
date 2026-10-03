"""ADR-0277 认知记忆扩展端口协议 (Cognitive Memory Extension Protocols).

定义工作记忆、开放知识图谱与 System 2 追忆检索的核心端口契约。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.cognition.memory.types import WorkingMemoryPercept


@runtime_checkable
class WorkingMemoryPort(Protocol):
    """工作记忆调度端口：管理单次 Run 内瞬态激活目标与焦点实体。"""

    def get_active_percept(self) -> WorkingMemoryPercept | None:
        """获取当前活跃的工作记忆感知。"""
        ...

    def update_percept(self, percept: WorkingMemoryPercept) -> None:
        """更新当前工作记忆感知。"""
        ...


@runtime_checkable
class EntityGraphPort(Protocol):
    """开放动态实体知识图谱端口：支持 Agent 自主构建多域实体网络与微索引。"""

    def write_entity(
        self,
        domain: str,
        slug: str,
        content: str,
        tags: tuple[str, ...] = (),
        aliases: tuple[str, ...] = (),
    ) -> None:
        """写入或更新实体页面，自动维护图关系微索引与 GC 预算。"""
        ...

    def read_entity(self, domain: str, slug: str) -> str | None:
        """读取指定实体的 Markdown 原文内容。"""
        ...

    def search_entities(self, query: str, limit: int = 10) -> list[str]:
        """通过派生索引全文检索实体 slug 列表。"""
        ...

    def get_active_graph_index(self) -> str:
        """获取 GRAPH.md 常驻微索引文本（Token 预算严格受控）。"""
        ...


@runtime_checkable
class InternalRecallPort(Protocol):
    """System 2 内部追忆端口：提供基于 ACT-R 激活扩散与多跳关系的自主深度检索。"""

    def recall(self, query: str, max_hops: int = 2) -> Any:
        """执行最多 max_hops 跳的关系扩散追忆，未命中诚实返回 NoRecall。"""
        ...
