"""Auto-generated surface skeleton for upstream ``session-query/session-query/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-query/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "SESSION_QUERY_DEFAULT_PERSISTED_INSPECT_CONCURRENCY",
    "SESSION_QUERY_READ_WINDOW_MAX",
    "Config",
    "SessionQueryEngine",
    "SessionQueryError",
    "SessionQueryErrorCode",
    "SessionSearchCursor",
    "assertSessionHeadersCompatible",
    "buildSessionEventRecords",
    "buildSessionEventSearchDocuments",
    "compileSessionTextFilter",
    "extractSessionEventText",
    "filterSessionEventDocuments",
    "filterSessionResults",
    "materializeSessionEventResultFilters",
    "materializeSessionResultFilters",
]

Config: TypeAlias = object  # port: surface stub

SessionQueryErrorCode: TypeAlias = object  # port: surface stub

class SessionQueryEngine:
    """Surface stub for upstream class ``SessionQueryEngine``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionQueryEngine.__init__ from session-query/session-query/src/index.ts")

SESSION_QUERY_DEFAULT_PERSISTED_INSPECT_CONCURRENCY = None  # port: surface stub (reexport)

SESSION_QUERY_READ_WINDOW_MAX = None  # port: surface stub (reexport)

SessionQueryError = None  # port: surface stub (reexport)

SessionSearchCursor = None  # port: surface stub (reexport)

assertSessionHeadersCompatible = None  # port: surface stub (reexport)

buildSessionEventRecords = None  # port: surface stub (reexport)

buildSessionEventSearchDocuments = None  # port: surface stub (reexport)

compileSessionTextFilter = None  # port: surface stub (reexport)

extractSessionEventText = None  # port: surface stub (reexport)

filterSessionEventDocuments = None  # port: surface stub (reexport)

filterSessionResults = None  # port: surface stub (reexport)

materializeSessionEventResultFilters = None  # port: surface stub (reexport)

materializeSessionResultFilters = None  # port: surface stub (reexport)
