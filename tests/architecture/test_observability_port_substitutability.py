"""Observability port substitution tests.

These tests pin the interface between the append-only journal and its attribute
policy.  A custom policy must be sufficient for the Journal write path; the
store must not require the default concrete policy implementation.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.journal import RuntimeObserved, StampedEvent
from lca.contracts.observability.ports import AttributePolicyBackend
from lca.infrastructure.observability.journal.engine import RunStore
from lca.infrastructure.observability.journal_backend import MemoryJournal


class _RecordingProjection:
    """Minimal projection implementation used to exercise the declared port."""

    def __init__(self) -> None:
        self.events: list[StampedEvent] = []

    def on_event(self, event: StampedEvent) -> None:
        self.events.append(event)


class _PrefixPolicy:
    """Minimal policy implementation used to exercise the declared port."""

    def prepare(self, attributes: dict[str, Any]) -> dict[str, Any]:
        return {key: f"prepared:{value}" for key, value in attributes.items()}

    def prepare_content(self, key: str, text: str) -> tuple[str | None, bool]:
        return (f"content:{key}:{text}", False)


def test_run_store_consumes_attribute_policy_port() -> None:
    """A policy implementing only the port shapes normal runtime attributes."""

    policy = _PrefixPolicy()
    assert isinstance(policy, AttributePolicyBackend)

    stamped = RunStore(policy=policy).append(
        RuntimeObserved(operation="test", attributes={"subject": "value"})
    )

    assert stamped is not None
    assert stamped.event.attributes == {"subject": "prepared:value"}


def test_memory_journal_consumes_event_projection_port() -> None:
    """A projection needs only ``on_event`` to observe committed journal facts."""

    projection = _RecordingProjection()
    event = RuntimeObserved(operation="test")
    stamped = MemoryJournal(projections=(projection,)).write(event)

    assert stamped is not None
    assert projection.events == [stamped]
