"""ContextManifest 的专用事实发射适配器。

感知 Hub 只构造 ``ContextManifested``；生产与测试共用 ``JournalSink``，
生产走 ``current_hub()``、测试可显式注入 store。不存在运行时双写开关或
第二条生产写入路径。
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


class JournalSink:
    """ContextManifest 统一进入事件账本：生产用 current_hub，测试可显式注入 store。"""

    def __init__(self, store: Any | None = None) -> None:
        self._store = store

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        store = self._store
        if store is None:
            from lca.layer0_infra.observability import current_bound

            bound = current_bound()
            if bound is None or bound.journal is None:
                return event
            store = bound.journal.store
        stamped = store.append(event)
        if stamped is None:
            return event
        return cast("ContextManifested", stamped.event)


def default_sink() -> ManifestSink:
    """返回生产账本适配器。"""
    return JournalSink()


__all__ = ["JournalSink", "ManifestSink", "NullSink", "default_sink"]
