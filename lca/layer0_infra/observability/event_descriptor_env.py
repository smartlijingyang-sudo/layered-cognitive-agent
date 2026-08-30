"""EventDescriptorRegistry 的 ambient 上下文（BoundObservability 同模式）。

Boot 期由 ``assemble_observability`` / ``assemble_run_hub`` 调
``bind_descriptors(registry)`` 装入，run 边所有 ``descriptor_for()``
默认读 ContextVar；无 ambient 时降级到 ``event_catalog`` 懒加载 fallback。

设计来源：与 ``facade._run_context`` / ``_bound`` 完全对称 —— ContextVar
在 asyncio.create_task 时自动 copy，子任务读到一致的 registry。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry

_event_descriptor_registry: ContextVar[EventDescriptorRegistry | None] = ContextVar(
    "lca_event_descriptor_registry", default=None
)


def current_descriptors() -> EventDescriptorRegistry | None:
    """读取当前 ambient EventDescriptorRegistry；未设置返回 None。"""
    return _event_descriptor_registry.get()


@contextmanager
def bind_descriptors(registry: EventDescriptorRegistry) -> Iterator[EventDescriptorRegistry]:
    """在 run 边缘激活 registry；嵌套不泄漏到外层。"""
    token = _event_descriptor_registry.set(registry)
    try:
        yield registry
    finally:
        _event_descriptor_registry.reset(token)


__all__ = ["bind_descriptors", "current_descriptors"]
