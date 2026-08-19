"""Auto-generated surface skeleton for upstream ``fs/fs-local/src/fsio.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/fs-local/src/fsio.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FsIoInternals",
    "LineEndings",
    "LocalDirEntry",
    "LocalTarget",
    "PathInfo",
    "PathLinkInfo",
    "applyLiteralEdit",
    "listDirectory",
    "normalizeLineEndings",
    "probe",
    "probeNoFollow",
    "readForEdit",
    "readTextForDiff",
    "readWholeBytes",
    "readWholeText",
    "resolveLocalTarget",
    "restoreLineEndings",
    "writeFileAtomic",
]

LineEndings: TypeAlias = object  # port: surface stub

def applyLiteralEdit(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyLiteralEdit``."""
    raise NotImplementedError("port applyLiteralEdit from fs/fs-local/src/fsio.ts")

def listDirectory(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``listDirectory``."""
    raise NotImplementedError("port listDirectory from fs/fs-local/src/fsio.ts")

def probe(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``probe``."""
    raise NotImplementedError("port probe from fs/fs-local/src/fsio.ts")

def probeNoFollow(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``probeNoFollow``."""
    raise NotImplementedError("port probeNoFollow from fs/fs-local/src/fsio.ts")

def readForEdit(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readForEdit``."""
    raise NotImplementedError("port readForEdit from fs/fs-local/src/fsio.ts")

def readTextForDiff(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readTextForDiff``."""
    raise NotImplementedError("port readTextForDiff from fs/fs-local/src/fsio.ts")

def readWholeBytes(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readWholeBytes``."""
    raise NotImplementedError("port readWholeBytes from fs/fs-local/src/fsio.ts")

def readWholeText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readWholeText``."""
    raise NotImplementedError("port readWholeText from fs/fs-local/src/fsio.ts")

def resolveLocalTarget(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveLocalTarget``."""
    raise NotImplementedError("port resolveLocalTarget from fs/fs-local/src/fsio.ts")

def writeFileAtomic(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``writeFileAtomic``."""
    raise NotImplementedError("port writeFileAtomic from fs/fs-local/src/fsio.ts")

normalizeLineEndings = None  # port: surface stub (reexport)

restoreLineEndings = None  # port: surface stub (reexport)

class FsIoInternals(Protocol):
    """Surface stub for upstream interface ``FsIoInternals``."""
    pass

class LocalDirEntry(Protocol):
    """Surface stub for upstream interface ``LocalDirEntry``."""
    pass

class LocalTarget(Protocol):
    """Surface stub for upstream interface ``LocalTarget``."""
    pass

class PathInfo(Protocol):
    """Surface stub for upstream interface ``PathInfo``."""
    pass

class PathLinkInfo(Protocol):
    """Surface stub for upstream interface ``PathLinkInfo``."""
    pass
