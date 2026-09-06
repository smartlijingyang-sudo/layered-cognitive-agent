"""Journal ledger append seam (ADR-0192 E4).

Cognition must not import ``facade.record`` directly. Legacy ``JournalEvent``
types not yet on the Session catalog append through this module until
delete-when clears remaining journal producers.

Kept outside ``journal/`` package to avoid eager RunStore imports on load.
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import JournalEvent, StampedEvent


def append_journal_event(event: JournalEvent) -> StampedEvent | None:
    """Append one catalog ``JournalEvent`` to the run ledger."""
    from lca.infrastructure.observability.facade.facade import record

    return record(event)


__all__ = ["append_journal_event"]
