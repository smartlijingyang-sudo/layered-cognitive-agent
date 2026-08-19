"""Auto-generated surface skeleton for upstream ``session/session-persistence/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_PREPARED_SESSION_CACHE_SIZE",
    "DEFAULT_WRITE_BATCH_MAX_DELAY_MS",
    "MAX_WRITE_BATCH_DELAY_MS",
    "PersistenceBackend",
    "PersistenceCoordinator",
    "PersistenceCoordinatorOptions",
    "SessionFormatUnsupportedError",
    "SessionHeader",
    "SessionInspection",
    "SessionLocation",
    "SessionPersistence",
    "SessionPersistenceCorruptionError",
    "SessionPersistenceRevision",
    "SessionPersistenceSnapshot",
    "SessionRawArtifact",
    "StoredPrefix",
    "StoredSuffix",
    "sessionFormatVersionRefusal",
]

PersistenceBackend: TypeAlias = object  # port: surface stub

PersistenceCoordinatorOptions: TypeAlias = object  # port: surface stub

SessionHeader: TypeAlias = object  # port: surface stub

StoredPrefix: TypeAlias = object  # port: surface stub

StoredSuffix: TypeAlias = object  # port: surface stub

class SessionPersistence:
    """Surface stub for upstream class ``SessionPersistence``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionPersistence.__init__ from session/session-persistence/src/index.ts")

DEFAULT_PREPARED_SESSION_CACHE_SIZE = None  # port: surface stub (reexport)

DEFAULT_WRITE_BATCH_MAX_DELAY_MS = None  # port: surface stub (reexport)

MAX_WRITE_BATCH_DELAY_MS = None  # port: surface stub (reexport)

PersistenceCoordinator = None  # port: surface stub (reexport)

SessionFormatUnsupportedError = None  # port: surface stub (reexport)

SessionPersistenceCorruptionError = None  # port: surface stub (reexport)

SessionPersistenceRevision = None  # port: surface stub (reexport)

sessionFormatVersionRefusal = None  # port: surface stub (reexport)

class SessionInspection(Protocol):
    """Surface stub for upstream interface ``SessionInspection``."""
    pass

class SessionLocation(Protocol):
    """Surface stub for upstream interface ``SessionLocation``."""
    pass

class SessionPersistenceSnapshot(Protocol):
    """Surface stub for upstream interface ``SessionPersistenceSnapshot``."""
    pass

class SessionRawArtifact(Protocol):
    """Surface stub for upstream interface ``SessionRawArtifact``."""
    pass
