"""Auto-generated surface skeleton for upstream ``extensions/ui-cordis/src/client/run-card-index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/ui-cordis/src/client/run-card-index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CordisRunCardPointer",
    "CordisRunCardRegistry",
    "CordisRunCardStore",
    "CordisToolViewKey",
    "cordisToolViewKey",
]

CordisToolViewKey: TypeAlias = object  # port: surface stub

def cordisToolViewKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``cordisToolViewKey``."""
    raise NotImplementedError("port cordisToolViewKey from extensions/ui-cordis/src/client/run-card-index.ts")

class CordisRunCardRegistry:
    """Surface stub for upstream class ``CordisRunCardRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CordisRunCardRegistry.__init__ from extensions/ui-cordis/src/client/run-card-index.ts")

class CordisRunCardPointer(Protocol):
    """Surface stub for upstream interface ``CordisRunCardPointer``."""
    pass

class CordisRunCardStore(Protocol):
    """Surface stub for upstream interface ``CordisRunCardStore``."""
    pass
