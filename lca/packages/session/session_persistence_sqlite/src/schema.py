"""Auto-generated surface skeleton for upstream ``session/session-persistence-sqlite/src/schema.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence-sqlite/src/schema.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SCHEMA_VERSION",
    "SESSION_PERSISTENCE_SQLITE_APPLICATION_ID",
    "EventRow",
    "JournalMode",
    "SessionRow",
    "openDatabase",
    "rowToEvent",
    "rowToMeta",
    "scanRows",
]

JournalMode: TypeAlias = object  # port: surface stub

SCHEMA_VERSION = None  # port: surface stub

SESSION_PERSISTENCE_SQLITE_APPLICATION_ID = None  # port: surface stub

def openDatabase(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``openDatabase``."""
    raise NotImplementedError("port openDatabase from session/session-persistence-sqlite/src/schema.ts")

def rowToEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``rowToEvent``."""
    raise NotImplementedError("port rowToEvent from session/session-persistence-sqlite/src/schema.ts")

def rowToMeta(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``rowToMeta``."""
    raise NotImplementedError("port rowToMeta from session/session-persistence-sqlite/src/schema.ts")

def scanRows(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scanRows``."""
    raise NotImplementedError("port scanRows from session/session-persistence-sqlite/src/schema.ts")

class EventRow(Protocol):
    """Surface stub for upstream interface ``EventRow``."""
    pass

class SessionRow(Protocol):
    """Surface stub for upstream interface ``SessionRow``."""
    pass
