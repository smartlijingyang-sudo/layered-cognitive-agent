"""Auto-generated surface skeleton for upstream ``session/session-persistence/src/coordinator.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence/src/coordinator.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DEFAULT_PREPARED_SESSION_CACHE_SIZE",
    "DEFAULT_WRITE_BATCH_MAX_DELAY_MS",
    "MAX_WRITE_BATCH_DELAY_MS",
    "PersistenceBackend",
    "PersistenceCoordinator",
    "PersistenceCoordinatorOptions",
    "SessionFormatUnsupportedError",
    "SessionPersistenceCorruptionError",
    "StoredPrefix",
    "StoredSuffix",
    "sessionFormatVersionRefusal",
]

DEFAULT_PREPARED_SESSION_CACHE_SIZE = None  # port: surface stub

DEFAULT_WRITE_BATCH_MAX_DELAY_MS = None  # port: surface stub

MAX_WRITE_BATCH_DELAY_MS = None  # port: surface stub

def sessionFormatVersionRefusal(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sessionFormatVersionRefusal``."""
    raise NotImplementedError("port sessionFormatVersionRefusal from session/session-persistence/src/coordinator.ts")

class PersistenceCoordinator:
    """Surface stub for upstream class ``PersistenceCoordinator``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PersistenceCoordinator.__init__ from session/session-persistence/src/coordinator.ts")

class SessionFormatUnsupportedError:
    """Surface stub for upstream class ``SessionFormatUnsupportedError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionFormatUnsupportedError.__init__ from session/session-persistence/src/coordinator.ts")

class SessionPersistenceCorruptionError:
    """Surface stub for upstream class ``SessionPersistenceCorruptionError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionPersistenceCorruptionError.__init__ from session/session-persistence/src/coordinator.ts")

class PersistenceBackend(Protocol):
    """Surface stub for upstream interface ``PersistenceBackend``."""
    pass

class PersistenceCoordinatorOptions(Protocol):
    """Surface stub for upstream interface ``PersistenceCoordinatorOptions``."""
    pass

class StoredPrefix(Protocol):
    """Surface stub for upstream interface ``StoredPrefix``."""
    pass

class StoredSuffix(Protocol):
    """Surface stub for upstream interface ``StoredSuffix``."""
    pass
