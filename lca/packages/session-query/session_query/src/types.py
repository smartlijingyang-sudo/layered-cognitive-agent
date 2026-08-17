"""Auto-generated surface skeleton for upstream ``session-query/session-query/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-query/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SessionAvailability",
    "SessionEventMetadataFilter",
    "SessionEventReadRequest",
    "SessionEventRecord",
    "SessionEventResultFilter",
    "SessionEventSearchDocument",
    "SessionEventSearchHit",
    "SessionEventSearchPage",
    "SessionEventSearchRequest",
    "SessionEventSurface",
    "SessionEventTrace",
    "SessionEventTraceObservation",
    "SessionEventTraceRequest",
    "SessionEventWindow",
    "SessionLineageNode",
    "SessionLineageTrace",
    "SessionLogSnapshot",
    "SessionRecord",
    "SessionResultFilter",
    "SessionResultRange",
    "SessionSearchCursor",
    "SessionSearchExecContext",
    "SessionSearchHit",
    "SessionSearchPage",
    "SessionSearchRequest",
    "SessionSurfaceSnapshot",
    "SessionTitleObservation",
    "SessionTitleObservationResult",
]

SessionAvailability: TypeAlias = object  # port: surface stub

SessionEventMetadataFilter: TypeAlias = object  # port: surface stub

SessionEventResultFilter: TypeAlias = object  # port: surface stub

SessionEventSurface: TypeAlias = object  # port: surface stub

SessionLineageTrace: TypeAlias = object  # port: surface stub

SessionResultFilter: TypeAlias = object  # port: surface stub

SessionSearchCursor: TypeAlias = object  # port: surface stub

SessionTitleObservationResult: TypeAlias = object  # port: surface stub

class SessionEventReadRequest(Protocol):
    """Surface stub for upstream interface ``SessionEventReadRequest``."""
    pass

class SessionEventRecord(Protocol):
    """Surface stub for upstream interface ``SessionEventRecord``."""
    pass

class SessionEventSearchDocument(Protocol):
    """Surface stub for upstream interface ``SessionEventSearchDocument``."""
    pass

class SessionEventSearchHit(Protocol):
    """Surface stub for upstream interface ``SessionEventSearchHit``."""
    pass

class SessionEventSearchPage(Protocol):
    """Surface stub for upstream interface ``SessionEventSearchPage``."""
    pass

class SessionEventSearchRequest(Protocol):
    """Surface stub for upstream interface ``SessionEventSearchRequest``."""
    pass

class SessionEventTrace(Protocol):
    """Surface stub for upstream interface ``SessionEventTrace``."""
    pass

class SessionEventTraceObservation(Protocol):
    """Surface stub for upstream interface ``SessionEventTraceObservation``."""
    pass

class SessionEventTraceRequest(Protocol):
    """Surface stub for upstream interface ``SessionEventTraceRequest``."""
    pass

class SessionEventWindow(Protocol):
    """Surface stub for upstream interface ``SessionEventWindow``."""
    pass

class SessionLineageNode(Protocol):
    """Surface stub for upstream interface ``SessionLineageNode``."""
    pass

class SessionLogSnapshot(Protocol):
    """Surface stub for upstream interface ``SessionLogSnapshot``."""
    pass

class SessionRecord(Protocol):
    """Surface stub for upstream interface ``SessionRecord``."""
    pass

class SessionResultRange(Protocol):
    """Surface stub for upstream interface ``SessionResultRange``."""
    pass

class SessionSearchExecContext(Protocol):
    """Surface stub for upstream interface ``SessionSearchExecContext``."""
    pass

class SessionSearchHit(Protocol):
    """Surface stub for upstream interface ``SessionSearchHit``."""
    pass

class SessionSearchPage(Protocol):
    """Surface stub for upstream interface ``SessionSearchPage``."""
    pass

class SessionSearchRequest(Protocol):
    """Surface stub for upstream interface ``SessionSearchRequest``."""
    pass

class SessionSurfaceSnapshot(Protocol):
    """Surface stub for upstream interface ``SessionSurfaceSnapshot``."""
    pass

class SessionTitleObservation(Protocol):
    """Surface stub for upstream interface ``SessionTitleObservation``."""
    pass
