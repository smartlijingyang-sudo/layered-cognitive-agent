"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/native-path-opener.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/native-path-opener.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PathOpenerInternals",
    "PathOpenerRunner",
    "canOpenNativePath",
    "openNativePath",
    "openNativeTextFile",
]

PathOpenerRunner: TypeAlias = object  # port: surface stub

def canOpenNativePath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``canOpenNativePath``."""
    raise NotImplementedError("port canOpenNativePath from host/apiproxy/src/native-path-opener.ts")

def openNativePath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``openNativePath``."""
    raise NotImplementedError("port openNativePath from host/apiproxy/src/native-path-opener.ts")

def openNativeTextFile(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``openNativeTextFile``."""
    raise NotImplementedError("port openNativeTextFile from host/apiproxy/src/native-path-opener.ts")

class PathOpenerInternals(Protocol):
    """Surface stub for upstream interface ``PathOpenerInternals``."""
    pass
