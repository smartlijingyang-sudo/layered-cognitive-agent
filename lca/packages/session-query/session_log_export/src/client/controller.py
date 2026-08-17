"""Auto-generated surface skeleton for upstream ``session-query/session-log-export/src/client/controller.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session-query/session-log-export/src/client/controller.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SessionLogDownloadController",
    "SessionLogDownloadEntry",
    "SessionLogDownloadState",
    "SessionLogDownloadStatus",
    "downloadUrl",
    "sessionLogZipFilename",
]

SessionLogDownloadStatus: TypeAlias = object  # port: surface stub

def downloadUrl(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``downloadUrl``."""
    raise NotImplementedError("port downloadUrl from session-query/session-log-export/src/client/controller.ts")

def sessionLogZipFilename(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sessionLogZipFilename``."""
    raise NotImplementedError("port sessionLogZipFilename from session-query/session-log-export/src/client/controller.ts")

class SessionLogDownloadController:
    """Surface stub for upstream class ``SessionLogDownloadController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionLogDownloadController.__init__ from session-query/session-log-export/src/client/controller.ts")

class SessionLogDownloadEntry(Protocol):
    """Surface stub for upstream interface ``SessionLogDownloadEntry``."""
    pass

class SessionLogDownloadState(Protocol):
    """Surface stub for upstream interface ``SessionLogDownloadState``."""
    pass
