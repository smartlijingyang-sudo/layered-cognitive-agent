"""In-process domain event publisher and the event vocabulary.

``InProcessEventPublisher`` is the default ``DomainEventPublisher`` adapter: it
delivers events to registered callbacks synchronously. Domain events are frozen
dataclasses so subscribers can pattern-match without coupling to the publisher.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher


@dataclass(frozen=True, slots=True)
class MemoryDomainEvent:
    """Base marker for context-files domain events."""


@dataclass(frozen=True, slots=True)
class ProjectionWritten(MemoryDomainEvent):
    """A curated ``MEMORY.md`` projection was atomically replaced on disk."""

    path: str
    byte_count: int
    record_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StandingPreserved(MemoryDomainEvent):
    """Injected standing blocks were rewritten from the current files."""

    names: tuple[str, ...]
    changed: bool


@dataclass(frozen=True, slots=True)
class ProjectionFailed(MemoryDomainEvent):
    """A curated projection could not be written; records stay in the JSON store."""

    path: str
    error: str
    record_ids: tuple[str, ...] = ()


class InProcessEventPublisher(DomainEventPublisher):
    """Publish ``MemoryDomainEvent`` instances to in-process subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[MemoryDomainEvent], None]] = []

    def subscribe(self, handler: Callable[[MemoryDomainEvent], None]) -> None:
        """Register a callback. Subscribing twice delivers twice."""
        self._subscribers.append(handler)

    def publish(self, event: object) -> None:
        if not isinstance(event, MemoryDomainEvent):
            return
        for handler in tuple(self._subscribers):
            handler(event)


__all__ = [
    "InProcessEventPublisher",
    "MemoryDomainEvent",
    "ProjectionFailed",
    "ProjectionWritten",
    "StandingPreserved",
]
