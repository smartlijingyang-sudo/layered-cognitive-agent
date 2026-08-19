"""Auto-generated surface skeleton for upstream ``session-query/session-query-sqlite/src/query.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-query-sqlite/src/query.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "FTS_HIGHLIGHT_END",
    "FTS_HIGHLIGHT_START",
    "SQLITE_FTS5_OUTER_PREDICATE_LIMIT",
    "SQLITE_MAX_PAGE_LIMIT",
    "SQLITE_PORTABLE_VARIABLE_LIMIT",
    "NormalizedEventRequest",
    "NormalizedSessionRequest",
    "QueryLimits",
    "SqlWhere",
    "assertFts5OuterPredicateCount",
    "assertPortableBindingCount",
    "buildEventWhere",
    "buildSessionWhere",
    "makeSnippet",
    "normalizeEventRequest",
    "normalizeSessionRequest",
    "quoteFtsData",
    "requestFingerprint",
    "sanitizeFtsText",
]

FTS_HIGHLIGHT_END = None  # port: surface stub

FTS_HIGHLIGHT_START = None  # port: surface stub

SQLITE_FTS5_OUTER_PREDICATE_LIMIT = None  # port: surface stub

SQLITE_MAX_PAGE_LIMIT = None  # port: surface stub

SQLITE_PORTABLE_VARIABLE_LIMIT = None  # port: surface stub

def assertFts5OuterPredicateCount(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertFts5OuterPredicateCount``."""
    raise NotImplementedError("port assertFts5OuterPredicateCount from session-query/session-query-sqlite/src/query.ts")

def assertPortableBindingCount(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertPortableBindingCount``."""
    raise NotImplementedError("port assertPortableBindingCount from session-query/session-query-sqlite/src/query.ts")

def buildEventWhere(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildEventWhere``."""
    raise NotImplementedError("port buildEventWhere from session-query/session-query-sqlite/src/query.ts")

def buildSessionWhere(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildSessionWhere``."""
    raise NotImplementedError("port buildSessionWhere from session-query/session-query-sqlite/src/query.ts")

def makeSnippet(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``makeSnippet``."""
    raise NotImplementedError("port makeSnippet from session-query/session-query-sqlite/src/query.ts")

def normalizeEventRequest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``normalizeEventRequest``."""
    raise NotImplementedError("port normalizeEventRequest from session-query/session-query-sqlite/src/query.ts")

def normalizeSessionRequest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``normalizeSessionRequest``."""
    raise NotImplementedError("port normalizeSessionRequest from session-query/session-query-sqlite/src/query.ts")

def quoteFtsData(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``quoteFtsData``."""
    raise NotImplementedError("port quoteFtsData from session-query/session-query-sqlite/src/query.ts")

def requestFingerprint(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``requestFingerprint``."""
    raise NotImplementedError("port requestFingerprint from session-query/session-query-sqlite/src/query.ts")

def sanitizeFtsText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sanitizeFtsText``."""
    raise NotImplementedError("port sanitizeFtsText from session-query/session-query-sqlite/src/query.ts")

class NormalizedEventRequest(Protocol):
    """Surface stub for upstream interface ``NormalizedEventRequest``."""
    pass

class NormalizedSessionRequest(Protocol):
    """Surface stub for upstream interface ``NormalizedSessionRequest``."""
    pass

class QueryLimits(Protocol):
    """Surface stub for upstream interface ``QueryLimits``."""
    pass

class SqlWhere(Protocol):
    """Surface stub for upstream interface ``SqlWhere``."""
    pass
