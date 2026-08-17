"""Auto-generated surface skeleton for upstream ``terminal/terminal/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``terminal/terminal/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TerminalBackend",
    "TerminalBackendCleanupError",
    "TerminalBackendSession",
    "TerminalBackendSpawnSpec",
    "TerminalError",
    "TerminalErrorCode",
    "TerminalReadRequest",
    "TerminalReadResult",
    "TerminalSendOperation",
    "TerminalSendRead",
    "TerminalSendRequest",
    "TerminalSendResult",
    "TerminalSessionId",
    "TerminalSessionService",
    "TerminalSessionSnapshot",
    "TerminalSessionStatus",
    "TerminalSignal",
    "TerminalSignalResult",
    "TerminalSpawnRequest",
    "TerminalSpawnResult",
    "TerminalWaitReason",
]

TerminalBackend: TypeAlias = object  # port: surface stub

TerminalBackendSession: TypeAlias = object  # port: surface stub

TerminalBackendSpawnSpec: TypeAlias = object  # port: surface stub

TerminalErrorCode: TypeAlias = object  # port: surface stub

TerminalReadRequest: TypeAlias = object  # port: surface stub

TerminalReadResult: TypeAlias = object  # port: surface stub

TerminalSendOperation: TypeAlias = object  # port: surface stub

TerminalSendRead: TypeAlias = object  # port: surface stub

TerminalSendRequest: TypeAlias = object  # port: surface stub

TerminalSendResult: TypeAlias = object  # port: surface stub

TerminalSessionId: TypeAlias = object  # port: surface stub

TerminalSessionSnapshot: TypeAlias = object  # port: surface stub

TerminalSessionStatus: TypeAlias = object  # port: surface stub

TerminalSignal: TypeAlias = object  # port: surface stub

TerminalSignalResult: TypeAlias = object  # port: surface stub

TerminalSpawnRequest: TypeAlias = object  # port: surface stub

TerminalSpawnResult: TypeAlias = object  # port: surface stub

TerminalWaitReason: TypeAlias = object  # port: surface stub

class TerminalError:
    """Surface stub for upstream class ``TerminalError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TerminalError.__init__ from terminal/terminal/src/index.ts")

class TerminalSessionService:
    """Surface stub for upstream class ``TerminalSessionService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TerminalSessionService.__init__ from terminal/terminal/src/index.ts")

TerminalBackendCleanupError = None  # port: surface stub (reexport)
