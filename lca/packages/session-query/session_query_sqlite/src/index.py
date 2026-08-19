"""Auto-generated surface skeleton for upstream ``session-query/session-query-sqlite/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-query-sqlite/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SESSION_QUERY_SQLITE_APPLICATION_ID",
    "SESSION_QUERY_SQLITE_DEFAULT_LIMIT",
    "SESSION_QUERY_SQLITE_MAX_LIMIT",
    "SESSION_QUERY_SQLITE_PATH_KEY",
    "SESSION_QUERY_SQLITE_SCHEMA_VERSION",
    "SESSION_QUERY_SQLITE_SNIPPET_CHARS",
    "Config",
    "JournalMode",
    "OpenAt",
    "SqliteSessionQueryEngine",
]

JournalMode: TypeAlias = object  # port: surface stub

OpenAt: TypeAlias = object  # port: surface stub

SESSION_QUERY_SQLITE_DEFAULT_LIMIT = None  # port: surface stub

SESSION_QUERY_SQLITE_MAX_LIMIT = None  # port: surface stub

SESSION_QUERY_SQLITE_PATH_KEY = None  # port: surface stub

SESSION_QUERY_SQLITE_SNIPPET_CHARS = None  # port: surface stub

class SqliteSessionQueryEngine:
    """Surface stub for upstream class ``SqliteSessionQueryEngine``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SqliteSessionQueryEngine.__init__ from session-query/session-query-sqlite/src/index.ts")

SESSION_QUERY_SQLITE_APPLICATION_ID = None  # port: surface stub (reexport)

SESSION_QUERY_SQLITE_SCHEMA_VERSION = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
