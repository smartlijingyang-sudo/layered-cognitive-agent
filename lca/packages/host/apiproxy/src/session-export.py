"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/session-export.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/session-export.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_SESSION_LOG_COMPRESSION_LEVEL",
    "SessionLogCompressionLevel",
    "SessionLogExportDeps",
    "SessionLogExportReady",
    "SessionLogZipEntry",
    "flushLiveSessionLog",
    "sessionLogExportDeps",
    "sessionLogZipFilename",
    "streamSessionLogZip",
]

SessionLogCompressionLevel: TypeAlias = object  # port: surface stub

SessionLogZipEntry: TypeAlias = object  # port: surface stub

DEFAULT_SESSION_LOG_COMPRESSION_LEVEL = None  # port: surface stub

def flushLiveSessionLog(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``flushLiveSessionLog``."""
    raise NotImplementedError("port flushLiveSessionLog from host/apiproxy/src/session-export.ts")

def sessionLogExportDeps(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sessionLogExportDeps``."""
    raise NotImplementedError("port sessionLogExportDeps from host/apiproxy/src/session-export.ts")

def sessionLogZipFilename(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sessionLogZipFilename``."""
    raise NotImplementedError("port sessionLogZipFilename from host/apiproxy/src/session-export.ts")

def streamSessionLogZip(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``streamSessionLogZip``."""
    raise NotImplementedError("port streamSessionLogZip from host/apiproxy/src/session-export.ts")

class SessionLogExportDeps(Protocol):
    """Surface stub for upstream interface ``SessionLogExportDeps``."""
    pass

class SessionLogExportReady(Protocol):
    """Surface stub for upstream interface ``SessionLogExportReady``."""
    pass
