"""Auto-generated surface skeleton for upstream ``storage/storage-sqlite/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-sqlite/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Config",
    "JournalMode",
    "STORAGE_SQLITE_SCHEMA_VERSION",
    "SqliteStorageBackend",
    "apply",
    "inject",
    "name",
]

JournalMode: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from storage/storage-sqlite/src/index.ts")

class SqliteStorageBackend:
    """Surface stub for upstream class ``SqliteStorageBackend``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SqliteStorageBackend.__init__ from storage/storage-sqlite/src/index.ts")

STORAGE_SQLITE_SCHEMA_VERSION = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
