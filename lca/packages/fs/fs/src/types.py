"""Auto-generated surface skeleton for upstream ``fs/fs/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/fs/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FsDirEntry",
    "FsEditOutcome",
    "FsEditRequest",
    "FsError",
    "FsErrorCode",
    "FsInfo",
    "FsObservation",
    "FsPathInfo",
    "FsTarget",
    "FsTargetKey",
    "FsVersion",
    "FsWriteIntent",
    "FsWriteOutcome",
]

FsErrorCode: TypeAlias = object  # port: surface stub

FsObservation: TypeAlias = object  # port: surface stub

FsTargetKey: TypeAlias = object  # port: surface stub

FsVersion: TypeAlias = object  # port: surface stub

FsWriteIntent: TypeAlias = object  # port: surface stub

class FsError:
    """Surface stub for upstream class ``FsError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port FsError.__init__ from fs/fs/src/types.ts")

class FsDirEntry(Protocol):
    """Surface stub for upstream interface ``FsDirEntry``."""
    pass

class FsEditOutcome(Protocol):
    """Surface stub for upstream interface ``FsEditOutcome``."""
    pass

class FsEditRequest(Protocol):
    """Surface stub for upstream interface ``FsEditRequest``."""
    pass

class FsInfo(Protocol):
    """Surface stub for upstream interface ``FsInfo``."""
    pass

class FsPathInfo(Protocol):
    """Surface stub for upstream interface ``FsPathInfo``."""
    pass

class FsTarget(Protocol):
    """Surface stub for upstream interface ``FsTarget``."""
    pass

class FsWriteOutcome(Protocol):
    """Surface stub for upstream interface ``FsWriteOutcome``."""
    pass
