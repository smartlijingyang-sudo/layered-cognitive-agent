"""Local ports the DSH driver talks to. Runtime contract is ``DshRuntime``."""

from __future__ import annotations

from typing import Protocol

from lca.contracts.models.observability.journal import JournalEvent
from lca.infrastructure.comparison.dsh_driver.models import DshNotification


class DshEventSink(Protocol):
    def emit(self, event: JournalEvent) -> None: ...


class DshEventArchive(Protocol):
    def append(self, notification: DshNotification) -> None: ...
