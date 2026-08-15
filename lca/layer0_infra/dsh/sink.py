"""Journal facade as a DSH event sink."""

from __future__ import annotations

from lca.contracts.models.observability.journal import JournalEvent
from lca.layer0_infra.observability import record


class FacadeJournalSink:
    def emit(self, event: JournalEvent) -> None:
        record(event)
