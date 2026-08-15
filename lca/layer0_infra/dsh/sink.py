"""Journal store as a DSH event sink（ADR-0055）。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.journal import JournalEvent


class HandleJournalSink:
    """DSH → RunStore sink with explicit hub reference。

    通过 store.append() 写入——跨线程安全，不依赖 ContextVar。
    显式 hub 优先（DSH 在子线程 + 新 event loop 中运行，ContextVar 不可靠）。
    """

    def __init__(self, hub: Any | None = None) -> None:
        self._hub = hub

    def emit(self, event: JournalEvent) -> None:
        hub = self._hub
        if hub is None:
            from lca.layer0_infra.observability import current_hub

            hub = current_hub()
        if hub is None:
            return
        hub.store.append(event)
