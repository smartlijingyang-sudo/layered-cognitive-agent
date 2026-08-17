"""Auto-generated surface skeleton for upstream ``session/session-persistence-sqlite/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence-sqlite/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "SCHEMA_VERSION",
    "SqliteSessionPersistence",
]

class SqliteSessionPersistence:
    """Surface stub for upstream class ``SqliteSessionPersistence``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SqliteSessionPersistence.__init__ from session/session-persistence-sqlite/src/index.ts")

SCHEMA_VERSION = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
