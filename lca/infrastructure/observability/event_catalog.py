"""事件描述符查询层（ADR-0063 PR-7 source inversion）。

三段式解析（ADR-0065 L4 收尾）：
1. **ambient 优先**——``descriptor_for()`` 先读 ``event_descriptor_env`` ContextVar；
   boot 路径由 ``assemble_observability`` / ``assemble_run_hub`` 注入。
2. **fallback**——ambient 为 None 时用本模块懒加载的 fallback registry
   （由 ``build_default_registry()`` 一次性构造），覆盖未 boot 的测试 / CLI 路径。
3. **fail-fast**——fallback 也无 → 抛 ``UnknownEventDescriptorError``（被 ``KeyError`` 包出）。

``EVENT_DESCRIPTOR_REGISTRY`` 保留为 PEP 562 懒加载符号，供测试与遗留 import
继续可用；生产代码应优先用 ``descriptor_for()`` + ambient ContextVar。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventSensitivity,
)
from lca.contracts.models.observability.journal import JournalEvent
from lca.infrastructure.observability.event_descriptor_env import current_descriptors
from lca.infrastructure.observability.event_descriptor_registry import (
    UnknownEventDescriptorError,
)
from lca.infrastructure.observability.event_descriptors_data import build_default_registry

if TYPE_CHECKING:
    from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry

# 懒加载 fallback：第一次读 EVENT_DESCRIPTOR_REGISTRY 时构造，后续复用同一对象。
# 与 ambient registry 完全独立——是兜底，不是替代品。
_fallback_cache: EventDescriptorRegistry | None = None


def _fallback_registry() -> EventDescriptorRegistry:
    global _fallback_cache
    if _fallback_cache is None:
        _fallback_cache = build_default_registry()
    return _fallback_cache


def _resolve_registry() -> EventDescriptorRegistry:
    """ambient 优先 → fallback；两条都没有就抛 KeyError。"""
    ambient = current_descriptors()
    if ambient is not None:
        return ambient
    return _fallback_registry()


def descriptor_for(event: JournalEvent | str) -> EventDescriptor:
    """返回已登记事件的唯一治理描述符。"""
    registry = _resolve_registry()
    type_name = event if isinstance(event, str) else type(event).__name__
    try:
        return registry.require(type_name)
    except UnknownEventDescriptorError as exc:
        raise KeyError(f"未登记的运行事件描述符：{type_name}") from exc


def may_export_externally(event: JournalEvent | str) -> bool:
    """外部 OTel/Langfuse 投影只接收非受限、非机密事件。"""
    descriptor = descriptor_for(event)
    return (
        descriptor.audience is not EventAudience.RESTRICTED
        and descriptor.sensitivity is not EventSensitivity.CONFIDENTIAL
    )


def __getattr__(name: str) -> Any:
    """PEP 562 懒加载导出（保留旧 API 兼容）。"""
    if name == "EVENT_DESCRIPTOR_REGISTRY":
        return _fallback_registry()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["EVENT_DESCRIPTOR_REGISTRY", "descriptor_for", "may_export_externally"]  # noqa: F822  (PEP 562 lazy export via __getattr__)
