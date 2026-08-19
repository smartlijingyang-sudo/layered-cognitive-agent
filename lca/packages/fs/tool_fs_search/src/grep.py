"""Auto-generated surface skeleton for upstream ``fs/tool-fs-search/src/grep.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs-search/src/grep.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "GREP_MAX_LINE_BYTES",
    "GREP_MAX_MATCHES",
    "GrepInput",
    "GrepToolCaps",
    "applyGrepTool",
    "buildGrepCommand",
    "formatGrepMatches",
    "formatGrepOutput",
    "parseGrepArgs",
    "parseGrepMatches",
    "presentGrepCall",
    "presentGrepResult",
]

GREP_MAX_LINE_BYTES = None  # port: surface stub

GREP_MAX_MATCHES = None  # port: surface stub

def applyGrepTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyGrepTool``."""
    raise NotImplementedError("port applyGrepTool from fs/tool-fs-search/src/grep.ts")

def buildGrepCommand(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``buildGrepCommand``."""
    raise NotImplementedError("port buildGrepCommand from fs/tool-fs-search/src/grep.ts")

def formatGrepMatches(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatGrepMatches``."""
    raise NotImplementedError("port formatGrepMatches from fs/tool-fs-search/src/grep.ts")

def formatGrepOutput(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatGrepOutput``."""
    raise NotImplementedError("port formatGrepOutput from fs/tool-fs-search/src/grep.ts")

def parseGrepArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseGrepArgs``."""
    raise NotImplementedError("port parseGrepArgs from fs/tool-fs-search/src/grep.ts")

def parseGrepMatches(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseGrepMatches``."""
    raise NotImplementedError("port parseGrepMatches from fs/tool-fs-search/src/grep.ts")

def presentGrepCall(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presentGrepCall``."""
    raise NotImplementedError("port presentGrepCall from fs/tool-fs-search/src/grep.ts")

def presentGrepResult(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``presentGrepResult``."""
    raise NotImplementedError("port presentGrepResult from fs/tool-fs-search/src/grep.ts")

class GrepInput(Protocol):
    """Surface stub for upstream interface ``GrepInput``."""
    pass

class GrepToolCaps(Protocol):
    """Surface stub for upstream interface ``GrepToolCaps``."""
    pass
