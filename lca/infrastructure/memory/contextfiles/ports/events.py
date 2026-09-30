"""Domain event publishing port.

The context-files architecture is observable through events: every projection
write, compaction application, watcher change or fault is published through
this port. LCA integration can subscribe and forward events into the session
journal; other agents can subscribe to the same publisher without knowing the
domain internals.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainEventPublisher(Protocol):
    """Publish a domain event to registered subscribers."""

    def publish(self, event: object) -> None: ...


__all__ = ["DomainEventPublisher"]
