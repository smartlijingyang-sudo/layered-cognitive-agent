"""Auto-generated surface skeleton for upstream ``fs/tool-fs-search/src/glob.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs-search/src/glob.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "GLOB_MAX_RESULTS",
    "GLOB_VCS_EXCLUDES",
    "GlobInput",
    "GlobSample",
    "GlobToolCaps",
    "applyGlobTool",
    "buildGlobCommand",
    "formatGlobOutput",
    "parseGlobArgs",
    "presentGlobCall",
    "presentGlobResult",
    "sampleAcrossTopLevel",
]

GLOB_MAX_RESULTS = None  # port: surface stub

GLOB_VCS_EXCLUDES = None  # port: surface stub

def applyGlobTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyGlobTool``."""
    raise NotImplementedError("port applyGlobTool from fs/tool-fs-search/src/glob.ts")

def buildGlobCommand(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildGlobCommand``."""
    raise NotImplementedError("port buildGlobCommand from fs/tool-fs-search/src/glob.ts")

def formatGlobOutput(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatGlobOutput``."""
    raise NotImplementedError("port formatGlobOutput from fs/tool-fs-search/src/glob.ts")

def parseGlobArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseGlobArgs``."""
    raise NotImplementedError("port parseGlobArgs from fs/tool-fs-search/src/glob.ts")

def presentGlobCall(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presentGlobCall``."""
    raise NotImplementedError("port presentGlobCall from fs/tool-fs-search/src/glob.ts")

def presentGlobResult(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presentGlobResult``."""
    raise NotImplementedError("port presentGlobResult from fs/tool-fs-search/src/glob.ts")

def sampleAcrossTopLevel(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sampleAcrossTopLevel``."""
    raise NotImplementedError("port sampleAcrossTopLevel from fs/tool-fs-search/src/glob.ts")

class GlobInput(Protocol):
    """Surface stub for upstream interface ``GlobInput``."""
    pass

class GlobSample(Protocol):
    """Surface stub for upstream interface ``GlobSample``."""
    pass

class GlobToolCaps(Protocol):
    """Surface stub for upstream interface ``GlobToolCaps``."""
    pass
