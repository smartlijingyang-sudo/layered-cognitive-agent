"""Auto-generated surface skeleton for upstream ``fs/tool-fs/src/read-render.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs/src/read-render.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FileReadOutcome",
    "FileTextLine",
    "FsReadMeta",
    "READ_MAX_BYTES",
    "READ_MAX_LINE_LENGTH",
    "ReadWindow",
    "WindowResult",
    "buildWindow",
    "formatReadOutput",
    "langFromPath",
    "readMetaFromMeta",
]

READ_MAX_BYTES = None  # port: surface stub

READ_MAX_LINE_LENGTH = None  # port: surface stub

def buildWindow(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildWindow``."""
    raise NotImplementedError("port buildWindow from fs/tool-fs/src/read-render.ts")

def formatReadOutput(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatReadOutput``."""
    raise NotImplementedError("port formatReadOutput from fs/tool-fs/src/read-render.ts")

def langFromPath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``langFromPath``."""
    raise NotImplementedError("port langFromPath from fs/tool-fs/src/read-render.ts")

def readMetaFromMeta(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readMetaFromMeta``."""
    raise NotImplementedError("port readMetaFromMeta from fs/tool-fs/src/read-render.ts")

class FileReadOutcome(Protocol):
    """Surface stub for upstream interface ``FileReadOutcome``."""
    pass

class FileTextLine(Protocol):
    """Surface stub for upstream interface ``FileTextLine``."""
    pass

class FsReadMeta(Protocol):
    """Surface stub for upstream interface ``FsReadMeta``."""
    pass

class ReadWindow(Protocol):
    """Surface stub for upstream interface ``ReadWindow``."""
    pass

class WindowResult(Protocol):
    """Surface stub for upstream interface ``WindowResult``."""
    pass
