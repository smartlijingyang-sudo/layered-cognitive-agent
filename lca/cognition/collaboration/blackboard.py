"""Blackboard Protocol + InMemoryBlackboard (PR9b.E.6).

Cross-agent fact-sharing surface for team coordination.  The blackboard
is intentionally simple:

- ``read(topic)`` returns entries in version order.
- ``append(topic, entry)`` writes a new entry with a monotonic
  per-topic version.
- ``cas(topic, expected_version, new_entry)`` performs a
  compare-and-set on the topic version (returns bool).
- ``acquire_lease / release_lease`` grant exclusive write rights to a
  holder for ``ttl_s`` seconds; a second acquisition is denied until
  release or expiry.

This is NOT a CRDT (per spec §9b).  Concurrent writers race on the
in-process mutex; the AST guard in ``tests/test_blackboard.py`` enforces
the no-CRDT rule.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


@dataclass(frozen=True)
class BlackboardEntry:
    """A single fact stored on the blackboard."""

    id: str
    topic: str
    version: int
    content: Any
    written_by: str
    lease_holder: str | None = None
    ttl_s: int | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Lease:
    """Exclusive write rights for a topic."""

    lease_id: str
    topic: str
    holder: str
    expires_at: float


@runtime_checkable
class Blackboard(Protocol):
    """Team-shared fact surface (cross-agent coordination)."""

    def read(self, topic: str) -> list[BlackboardEntry]: ...

    def append(self, topic: str, entry: dict[str, Any]) -> BlackboardEntry: ...

    def cas(
        self,
        topic: str,
        *,
        expected_version: int,
        new_entry: dict[str, Any],
    ) -> bool: ...

    def acquire_lease(
        self,
        topic: str,
        *,
        holder: str,
        ttl_s: int,
    ) -> Lease | None: ...

    def release_lease(self, lease: Lease) -> None: ...


class InMemoryBlackboard(Blackboard):
    """Single-process implementation.

    Concurrency: a process-wide ``threading.Lock`` guards all mutations.
    The lock is held briefly so tests can run deterministically without
    sleeps.  Production paths that need cross-process semantics should
    layer a real CRDT or DB-backed implementation on top of the
    ``Blackboard`` Protocol.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, list[BlackboardEntry]] = {}
        self._leases: dict[str, Lease] = {}

    # ── read / cas ────────────────────────────────────────────

    def read(self, topic: str) -> list[BlackboardEntry]:
        with self._lock:
            return list(self._entries.get(topic, ()))

    def _current_version(self, topic: str) -> int:
        entries = self._entries.get(topic)
        return entries[-1].version if entries else 0

    def append(self, topic: str, entry: dict[str, Any]) -> BlackboardEntry:
        with self._lock:
            next_version = self._current_version(topic) + 1
            blackboard_entry = BlackboardEntry(
                id=str(uuid4()),
                topic=topic,
                version=next_version,
                content=entry.get("content"),
                written_by=str(entry.get("written_by", "")),
                lease_holder=entry.get("lease_holder"),
                ttl_s=entry.get("ttl_s"),
            )
            self._entries.setdefault(topic, []).append(blackboard_entry)
            return blackboard_entry

    def cas(
        self,
        topic: str,
        *,
        expected_version: int,
        new_entry: dict[str, Any],
    ) -> bool:
        with self._lock:
            if self._current_version(topic) != expected_version:
                return False
            next_version = expected_version + 1
            blackboard_entry = BlackboardEntry(
                id=str(uuid4()),
                topic=topic,
                version=next_version,
                content=new_entry.get("content"),
                written_by=str(new_entry.get("written_by", "")),
                lease_holder=new_entry.get("lease_holder"),
                ttl_s=new_entry.get("ttl_s"),
            )
            self._entries.setdefault(topic, []).append(blackboard_entry)
            return True

    # ── leases ────────────────────────────────────────────────

    def acquire_lease(
        self,
        topic: str,
        *,
        holder: str,
        ttl_s: int,
    ) -> Lease | None:
        with self._lock:
            existing = self._leases.get(topic)
            if existing is not None and existing.expires_at > time.time():
                return None
            lease = Lease(
                lease_id=str(uuid4()),
                topic=topic,
                holder=holder,
                expires_at=time.time() + max(ttl_s, 0),
            )
            self._leases[topic] = lease
            return lease

    def release_lease(self, lease: Lease) -> None:
        with self._lock:
            existing = self._leases.get(lease.topic)
            if existing is not None and existing.lease_id == lease.lease_id:
                del self._leases[lease.topic]


__all__ = [
    "Blackboard",
    "BlackboardEntry",
    "InMemoryBlackboard",
    "Lease",
]
