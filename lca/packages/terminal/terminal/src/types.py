"""Auto-generated surface skeleton for upstream ``terminal/terminal/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``terminal/terminal/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TerminalBackend",
    "TerminalBackendCleanupError",
    "TerminalBackendSession",
    "TerminalBackendSpawnSpec",
    "TerminalReadRequest",
    "TerminalReadResult",
    "TerminalSendOperation",
    "TerminalSendRead",
    "TerminalSendRequest",
    "TerminalSendResult",
    "TerminalSessionIdValue",
    "TerminalSessionSnapshot",
    "TerminalSessionStatus",
    "TerminalSignal",
    "TerminalSignalResult",
    "TerminalSpawnRequest",
    "TerminalSpawnResult",
    "TerminalWaitReason",
]

TerminalSessionIdValue: TypeAlias = object  # port: surface stub

TerminalSessionStatus: TypeAlias = object  # port: surface stub

TerminalSignal: TypeAlias = object  # port: surface stub

TerminalWaitReason: TypeAlias = object  # port: surface stub

class TerminalBackendCleanupError:
    """Surface stub for upstream class ``TerminalBackendCleanupError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TerminalBackendCleanupError.__init__ from terminal/terminal/src/types.ts")

class TerminalBackend(Protocol):
    """Surface stub for upstream interface ``TerminalBackend``."""
    pass

class TerminalBackendSession(Protocol):
    """Surface stub for upstream interface ``TerminalBackendSession``."""
    pass

class TerminalBackendSpawnSpec(Protocol):
    """Surface stub for upstream interface ``TerminalBackendSpawnSpec``."""
    pass

class TerminalReadRequest(Protocol):
    """Surface stub for upstream interface ``TerminalReadRequest``."""
    pass

class TerminalReadResult(Protocol):
    """Surface stub for upstream interface ``TerminalReadResult``."""
    pass

class TerminalSendOperation(Protocol):
    """Surface stub for upstream interface ``TerminalSendOperation``."""
    pass

class TerminalSendRead(Protocol):
    """Surface stub for upstream interface ``TerminalSendRead``."""
    pass

class TerminalSendRequest(Protocol):
    """Surface stub for upstream interface ``TerminalSendRequest``."""
    pass

class TerminalSendResult(Protocol):
    """Surface stub for upstream interface ``TerminalSendResult``."""
    pass

class TerminalSessionSnapshot(Protocol):
    """Surface stub for upstream interface ``TerminalSessionSnapshot``."""
    pass

class TerminalSignalResult(Protocol):
    """Surface stub for upstream interface ``TerminalSignalResult``."""
    pass

class TerminalSpawnRequest(Protocol):
    """Surface stub for upstream interface ``TerminalSpawnRequest``."""
    pass

class TerminalSpawnResult(Protocol):
    """Surface stub for upstream interface ``TerminalSpawnResult``."""
    pass
