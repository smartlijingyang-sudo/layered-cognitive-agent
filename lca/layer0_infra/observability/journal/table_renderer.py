"""journal 渲染共享工具（ADR-0063 清理 B）。

ConsoleJournalProjector / FactStreamProjector / JsonlJournalProjector 各有自己的
渲染细节；它们不需要合并到一个巨型 class，但应共享最小工具集：
- 文本截断（统一上限）
- 容器 vs 叙事事件分类（按 EventDescriptor.plane）
- section header 行为

本模块提供上述纯函数，让后续插件（JOURNAL_FORMATTER seam）能复用同一基础。
"""

from __future__ import annotations

from lca.contracts.models.observability.event import EventPlane
from lca.contracts.models.observability.journal import JournalEvent
from lca.layer0_infra.observability.event_catalog import descriptor_for


def truncate(text: str, max_len: int) -> str:
    """超长截断（保留前缀 + 省略号）。所有 renderer 共用。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def is_surface_event(event: JournalEvent) -> bool:
    """事件是否属于 Surface 平面（用户/模型可见）。"""
    return descriptor_for(event).plane is EventPlane.SURFACE


def is_structural_event(event: JournalEvent) -> bool:
    """事件是否属于 Structural 平面（生命周期）。"""
    return descriptor_for(event).plane is EventPlane.STRUCTURAL


def is_explanation_event(event: JournalEvent) -> bool:
    """事件是否属于 Explanation 平面（RuntimeObserved）。"""
    return descriptor_for(event).plane is EventPlane.EXPLANATION
