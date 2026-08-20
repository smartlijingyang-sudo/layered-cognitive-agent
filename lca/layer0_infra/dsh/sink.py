"""Journal store as a DSH event sink（ADR-0055）。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.journal import JournalEvent


class HandleJournalSink:
    """DSH → RunStore sink with explicit bound reference。

    通过 store.append() 写入——跨线程安全，不依赖 ContextVar。
    显式 bound 优先（DSH 在子线程 + 新 event loop 中运行，ContextVar 不可靠）。
    """

    def __init__(self, bound: Any | None = None) -> None:
        self._bound = bound

    def emit(self, event: JournalEvent) -> None:
        bound = self._bound
        if bound is None:
            from lca.layer0_infra.observability import current_bound

            bound = current_bound()
        if bound is None or bound.journal is None:
            return
        bound.journal.store.append(event)
