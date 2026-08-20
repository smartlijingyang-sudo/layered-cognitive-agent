"""ContextManifest 的专用事实发射适配器。

感知 Hub 只构造 ``ContextManifested``；生产适配器调用统一 ``record`` 入口，
测试可注入 ``RunStoreSink``。不存在运行时双写开关或第二条生产写入路径。
"""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.observability.journal import ContextManifested


@runtime_checkable
class ManifestSink(Protocol):
    """把已构造的 ContextManifest 事实追加到调用方指定的事件账本。"""

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested: ...


class NullSink:
    """离线或无 Journal 测试的 no-op 适配器。"""

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        return event


class RunStoreSink:
    """测试和显式组合使用的账本适配器。"""

    def __init__(self, store: Any) -> None:
        self._store = store

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        stamped = self._store.append(event)
        return cast("ContextManifested", stamped.event)


class JournalSink:
    """生产适配器：所有 ContextManifest 统一进入主事件账本。"""

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        from lca.layer0_infra.observability import current_hub

        hub = current_hub()
        stamped = hub.store.append(event) if hub is not None else None
        return cast("ContextManifested", stamped.event) if stamped is not None else event


def default_sink() -> ManifestSink:
    """返回生产账本适配器。"""
    return JournalSink()
