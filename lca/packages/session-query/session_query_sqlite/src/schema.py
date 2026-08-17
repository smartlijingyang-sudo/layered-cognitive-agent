"""Auto-generated surface skeleton for upstream ``session-query/session-query-sqlite/src/schema.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-query-sqlite/src/schema.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "JournalMode",
    "SESSION_QUERY_SQLITE_APPLICATION_ID",
    "SESSION_QUERY_SQLITE_SCHEMA_VERSION",
    "openSearchDatabase",
]

JournalMode: TypeAlias = object  # port: surface stub

SESSION_QUERY_SQLITE_APPLICATION_ID = None  # port: surface stub

SESSION_QUERY_SQLITE_SCHEMA_VERSION = None  # port: surface stub

def openSearchDatabase(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``openSearchDatabase``."""
    raise NotImplementedError("port openSearchDatabase from session-query/session-query-sqlite/src/schema.ts")
