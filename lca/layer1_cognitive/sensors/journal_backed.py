"""Journal-backed sensor base class (PR8 / PR9).

The inbox and team-inbox sensors share the same pattern: read events of
a specific ``JournalEvent`` subclass from the ``RunStore`` and project
them into a list of dicts.  This module captures the shared structure
so adding a new journal-backed sensor is a single-class declaration.

The sensors deliberately read from the local ``RunStore.events`` list
(not the cached ``derive_events`` projection) — the cache is keyed by
predicate id and would otherwise leak state across sensors in the same
process.  Volume is small (one event per arrive) so the linear scan is
fine.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterator
from typing import Any

from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import (
    InboxFollowupCreated,
    StampedEvent,
    TeamMessagePublished,
)
from lca.contracts.models.observability.journal import (
    JournalEvent as _JournalEvent,
)
from lca.contracts.protocols import Sensor
from lca.layer0_infra.observability import RunStore

# Item kind identifiers (closed set, see perception.py).
INBOX_FACTS_KIND = "inbox_facts"
TEAM_INBOX_KIND = "team_inbox"


class _JournalSensor(Sensor):
    """Base class for sensors that project a specific journal event class.

    Subclasses declare:
    - ``event_cls``: the ``JournalEvent`` subclass to fold
    - ``item_kind``: the ``ContextItem.kind`` to emit
    - ``provenance``: the ``ContextItem.provenance`` name
    - ``_project``: how to project a stamped event to a ``dict``
    """

    event_cls: type[_JournalEvent]
    item_kind: str
    provenance: str

    def __init__(self, store: RunStore, *, since_step: int = 0) -> None:
        self._store = store
        self._since_step = since_step

    async def read(self, state: AgentState) -> list[ContextItem]:
        events = list(self._iter_events())
        if not events:
            return []
        return [
            ContextItem(
                kind=self.item_kind,
                payload=[self._project(e) for e in events],
                provenance=self.provenance,
            )
        ]

    def _iter_events(self) -> Iterator[StampedEvent]:
        for stamped in self._store.events:
            event = stamped.event
            if isinstance(event, self.event_cls) and event.step >= self._since_step:
                yield stamped

    @abstractmethod
    def _project(self, event: StampedEvent) -> dict[str, Any]:
        ...


class InboxFactsSensor(_JournalSensor):
    """Fold ``InboxFollowupCreated`` events into an ``inbox_facts`` item (PR8)."""

    event_cls = InboxFollowupCreated
    item_kind = INBOX_FACTS_KIND
    provenance = "inbox_facts_sensor"

    def _project(self, event: StampedEvent) -> dict[str, Any]:
        assert isinstance(event.event, InboxFollowupCreated)
        return {
            "inbox_id": event.event.inbox_id,
            "actor": event.event.actor,
            "target": event.event.target,
            "priority": event.event.priority,
            "payload_preview": event.event.payload_preview,
            "seq": event.seq,
        }


def build_inbox_facts_sensor(store: RunStore) -> Sensor:
    """Named factory: ``sensor.inbox-facts`` (PR8)."""
    return InboxFactsSensor(store)


class TeamInboxSensor(_JournalSensor):
    """Fold ``TeamMessagePublished`` events into a ``team_inbox`` item (PR9)."""

    event_cls = TeamMessagePublished
    item_kind = TEAM_INBOX_KIND
    provenance = "team_inbox_sensor"

    def _project(self, event: StampedEvent) -> dict[str, Any]:
        assert isinstance(event.event, TeamMessagePublished)
        return {
            "team_id": event.event.team_id,
            "thread_id": event.event.thread_id,
            "sender_role": event.event.sender_role,
            "recipient_role": event.event.recipient_role,
            "body_preview": event.event.body_preview,
            "seq": event.seq,
        }


def build_team_inbox_sensor(store: RunStore) -> Sensor:
    """Named factory: ``sensor.team-inbox`` (PR9)."""
    return TeamInboxSensor(store)
