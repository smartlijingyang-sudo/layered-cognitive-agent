"""Auto-generated surface skeleton for upstream ``core/session/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/session/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "KNOWN_SESSION_EVENT_TYPES",
    "TOOL_NOT_STARTED",
    "TOOL_OUTCOME_UNKNOWN",
    "AssistantMessage",
    "ChunkRow",
    "JsonValue",
    "Session",
    "SessionForkError",
    "SessionForkErrorCode",
    "SessionForkSource",
    "SessionPreparation",
    "SessionPreparationOptions",
    "SessionStore",
    "SessionSurface",
    "StorageRecord",
    "SurfaceFoldReplacement",
    "SurfaceFoldResult",
    "ToolResultMessage",
    "UserMessage",
    "adoptSessionEvent",
    "canonicalHeader",
    "decodeStorageRecord",
    "deriveEventMessage",
    "foldRequestHeader",
    "foldSurface",
    "headerEquals",
    "interruptedTurnClosers",
    "isAppendSurfaceEvent",
    "isJsonValue",
    "isReplacementSurfaceEvent",
    "isSurfaceEligibleType",
    "isSurfaceEvent",
    "packChunkRuns",
    "snapshotJsonValue",
    "snapshotSessionEvent",
]

AssistantMessage: TypeAlias = object  # port: surface stub

ChunkRow: TypeAlias = object  # port: surface stub

JsonValue: TypeAlias = object  # port: surface stub

SessionForkErrorCode: TypeAlias = object  # port: surface stub

SessionForkSource: TypeAlias = object  # port: surface stub

SessionPreparationOptions: TypeAlias = object  # port: surface stub

SessionSurface: TypeAlias = object  # port: surface stub

StorageRecord: TypeAlias = object  # port: surface stub

SurfaceFoldReplacement: TypeAlias = object  # port: surface stub

SurfaceFoldResult: TypeAlias = object  # port: surface stub

ToolResultMessage: TypeAlias = object  # port: surface stub

UserMessage: TypeAlias = object  # port: surface stub

def adoptSessionEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``adoptSessionEvent``."""
    raise NotImplementedError("port adoptSessionEvent from core/session/src/index.ts")

def snapshotSessionEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``snapshotSessionEvent``."""
    raise NotImplementedError("port snapshotSessionEvent from core/session/src/index.ts")

class Session:
    """Surface stub for upstream class ``Session``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port Session.__init__ from core/session/src/index.ts")

class SessionForkError:
    """Surface stub for upstream class ``SessionForkError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionForkError.__init__ from core/session/src/index.ts")

class SessionStore:
    """Surface stub for upstream class ``SessionStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionStore.__init__ from core/session/src/index.ts")

KNOWN_SESSION_EVENT_TYPES = None  # port: surface stub (reexport)

SessionPreparation = None  # port: surface stub (reexport)

TOOL_NOT_STARTED = None  # port: surface stub (reexport)

TOOL_OUTCOME_UNKNOWN = None  # port: surface stub (reexport)

canonicalHeader = None  # port: surface stub (reexport)

decodeStorageRecord = None  # port: surface stub (reexport)

deriveEventMessage = None  # port: surface stub (reexport)

foldRequestHeader = None  # port: surface stub (reexport)

foldSurface = None  # port: surface stub (reexport)

headerEquals = None  # port: surface stub (reexport)

interruptedTurnClosers = None  # port: surface stub (reexport)

isAppendSurfaceEvent = None  # port: surface stub (reexport)

isJsonValue = None  # port: surface stub (reexport)

isReplacementSurfaceEvent = None  # port: surface stub (reexport)

isSurfaceEligibleType = None  # port: surface stub (reexport)

isSurfaceEvent = None  # port: surface stub (reexport)

packChunkRuns = None  # port: surface stub (reexport)

snapshotJsonValue = None  # port: surface stub (reexport)
