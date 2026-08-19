"""Auto-generated surface skeleton for upstream ``storage/storage-sqlite/src/schema.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-sqlite/src/schema.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "STORAGE_SQLITE_SCHEMA_VERSION",
    "JournalMode",
    "openDatabase",
    "recordTableName",
]

JournalMode: TypeAlias = object  # port: surface stub

STORAGE_SQLITE_SCHEMA_VERSION = None  # port: surface stub

def openDatabase(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``openDatabase``."""
    raise NotImplementedError("port openDatabase from storage/storage-sqlite/src/schema.ts")

def recordTableName(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``recordTableName``."""
    raise NotImplementedError("port recordTableName from storage/storage-sqlite/src/schema.ts")
