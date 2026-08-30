"""Contracts for profile-selected durable Session persistence.

The Session Spine owns one live agent per Session, but storage implementation is
an infrastructure choice.  These protocols let a profile select JSONL, a
database, or an event-store backend without embedding that choice in
``AgentRegistry``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.contracts.harness.session import SessionEvent, SessionHeader


@runtime_checkable
class SessionPersistence(Protocol):
    """Append and recover the durable facts for exactly one Session."""

    def write_header(self, header: SessionHeader) -> None: ...

    def write_event(self, event: SessionEvent) -> None: ...

    def load(self) -> tuple[SessionHeader | None, list[SessionEvent]]: ...

    def local_path(self) -> Path | None:
        """Return a local artifact path when this backend exposes one, else ``None``."""


@runtime_checkable
class SessionPersistenceFactory(Protocol):
    """Create the backend selected for a Session's durable fact stream."""

    def create(self, *, session_id: str, sessions_dir: Path) -> SessionPersistence: ...


__all__ = ["SessionPersistence", "SessionPersistenceFactory"]
