"""Auto-generated surface skeleton for upstream ``core/session/src/surface.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/session/src/surface.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SessionSurface",
    "SurfaceFoldReplacement",
    "SurfaceFoldResult",
    "SurfaceManager",
    "deriveEventMessage",
    "foldSurface",
    "isAppendSurfaceEvent",
    "isReplacementSurfaceEvent",
    "isSurfaceEligibleType",
    "isSurfaceEvent",
]

def deriveEventMessage(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveEventMessage``."""
    raise NotImplementedError("port deriveEventMessage from core/session/src/surface.ts")

def foldSurface(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``foldSurface``."""
    raise NotImplementedError("port foldSurface from core/session/src/surface.ts")

def isAppendSurfaceEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isAppendSurfaceEvent``."""
    raise NotImplementedError("port isAppendSurfaceEvent from core/session/src/surface.ts")

def isReplacementSurfaceEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isReplacementSurfaceEvent``."""
    raise NotImplementedError("port isReplacementSurfaceEvent from core/session/src/surface.ts")

def isSurfaceEligibleType(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isSurfaceEligibleType``."""
    raise NotImplementedError("port isSurfaceEligibleType from core/session/src/surface.ts")

def isSurfaceEvent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isSurfaceEvent``."""
    raise NotImplementedError("port isSurfaceEvent from core/session/src/surface.ts")

class SurfaceManager:
    """Surface stub for upstream class ``SurfaceManager``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SurfaceManager.__init__ from core/session/src/surface.ts")

class SessionSurface(Protocol):
    """Surface stub for upstream interface ``SessionSurface``."""
    pass

class SurfaceFoldReplacement(Protocol):
    """Surface stub for upstream interface ``SurfaceFoldReplacement``."""
    pass

class SurfaceFoldResult(Protocol):
    """Surface stub for upstream interface ``SurfaceFoldResult``."""
    pass
