"""Auto-generated surface skeleton for upstream ``fs/tool-fs/src/read.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``fs/tool-fs/src/read.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "READ_LIMIT",
    "ReadToolCaps",
    "STREAM_MIN_SIZE",
    "applyReadTool",
    "parseReadArgs",
]

READ_LIMIT = None  # port: surface stub

STREAM_MIN_SIZE = None  # port: surface stub

def applyReadTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyReadTool``."""
    raise NotImplementedError("port applyReadTool from fs/tool-fs/src/read.ts")

def parseReadArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseReadArgs``."""
    raise NotImplementedError("port parseReadArgs from fs/tool-fs/src/read.ts")

class ReadToolCaps(Protocol):
    """Surface stub for upstream interface ``ReadToolCaps``."""
    pass
