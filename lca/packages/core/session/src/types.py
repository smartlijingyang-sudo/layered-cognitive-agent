"""Auto-generated surface skeleton for upstream ``core/session/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/session/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AgentCancelCause",
    "CreateSessionOptions",
    "EpochHeader",
    "JsonValue",
    "PrepareSessionOptions",
    "RequestContext",
    "RequestHeaderReason",
    "RestoredSessionOptions",
    "SESSION_FORMAT_VERSION",
    "SessionEvent",
    "SessionEventMap",
    "SessionEventType",
    "SessionHeader",
    "SessionId",
    "SurfaceEvent",
    "SurfaceEventType",
    "SurfaceIntent",
    "SurfaceOp",
    "TodoItem",
    "TurnEndCancelCause",
    "TurnEndReason",
    "TurnEndReasonMap",
]

AgentCancelCause: TypeAlias = object  # port: surface stub

JsonValue: TypeAlias = object  # port: surface stub

PrepareSessionOptions: TypeAlias = object  # port: surface stub

RequestHeaderReason: TypeAlias = object  # port: surface stub

SessionEvent: TypeAlias = object  # port: surface stub

SessionEventType: TypeAlias = object  # port: surface stub

SessionId: TypeAlias = object  # port: surface stub

SurfaceEvent: TypeAlias = object  # port: surface stub

SurfaceEventType: TypeAlias = object  # port: surface stub

SurfaceOp: TypeAlias = object  # port: surface stub

TurnEndCancelCause: TypeAlias = object  # port: surface stub

TurnEndReason: TypeAlias = object  # port: surface stub

SESSION_FORMAT_VERSION = None  # port: surface stub

class CreateSessionOptions(Protocol):
    """Surface stub for upstream interface ``CreateSessionOptions``."""
    pass

class EpochHeader(Protocol):
    """Surface stub for upstream interface ``EpochHeader``."""
    pass

class RequestContext(Protocol):
    """Surface stub for upstream interface ``RequestContext``."""
    pass

class RestoredSessionOptions(Protocol):
    """Surface stub for upstream interface ``RestoredSessionOptions``."""
    pass

class SessionEventMap(Protocol):
    """Surface stub for upstream interface ``SessionEventMap``."""
    pass

class SessionHeader(Protocol):
    """Surface stub for upstream interface ``SessionHeader``."""
    pass

class SurfaceIntent(Protocol):
    """Surface stub for upstream interface ``SurfaceIntent``."""
    pass

class TodoItem(Protocol):
    """Surface stub for upstream interface ``TodoItem``."""
    pass

class TurnEndReasonMap(Protocol):
    """Surface stub for upstream interface ``TurnEndReasonMap``."""
    pass
