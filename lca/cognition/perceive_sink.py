"""ContextManifest journal sink adapters (COMPAT — ADR-0192 E4 delete-when).

PerceiveHub no longer emits facts; production uses ``PhaseFactEmitter`` +
``emit_context_manifested_for_state``. ``JournalSink`` remains for tests that
assert legacy ``ContextManifested`` journal records until delete-when clears.
"""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.observability.journal import (
    ContextManifested,
    JournalEvent,
    StampedEvent,
)
from lca.contracts.observability.ports import JournalBackend


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


class JournalEventAppender(Protocol):
    """测试适配器所需的最小 append-only 存储 interface。"""

    def append(self, event: JournalEvent) -> StampedEvent | None: ...


class _StoreBackedJournal:
    """把专注测试中的 append-only 存储适配为 JournalBackend。"""

    def __init__(self, store: JournalEventAppender) -> None:
        self._store = store

    def write(self, event: JournalEvent) -> StampedEvent | None:
        return self._store.append(event)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class JournalSink:
    """将 ContextManifest 写入 :class:`JournalBackend` 的专用适配器。

    生产路径从当前观测 Hub 取得账本端口；测试也应注入同一端口，而非穿透
    到 ``RunStore``。这样感知模块只依赖 ``write`` 这一稳定 interface，存储、
    投影与属性策略仍由 JournalBackend 在其内部封装。
    """

    def __init__(self, journal: JournalBackend | None = None) -> None:
        self._journal = journal

    @classmethod
    def for_store(cls, store: JournalEventAppender) -> JournalSink:
        """显式适配 append-only 存储，供需要检查原始事件的专注测试使用。"""

        return cls(_StoreBackedJournal(store))

    def emit(
        self,
        event: ContextManifested,
        manifest: ContextManifest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ContextManifested:
        journal = self._journal
        if journal is None:
            from lca.infrastructure.observability import current_bound

            bound = current_bound()
            if bound is None or bound.journal is None:
                return event
            journal = bound.journal
        stamped = journal.write(event)
        if stamped is None:
            return event
        return cast("ContextManifested", stamped.event)


def default_sink() -> ManifestSink:
    """返回生产账本适配器。"""
    return JournalSink()


__all__ = [
    "JournalEventAppender",
    "JournalSink",
    "ManifestSink",
    "NullSink",
    "default_sink",
]
