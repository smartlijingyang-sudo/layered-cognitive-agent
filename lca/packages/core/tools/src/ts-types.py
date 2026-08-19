"""Auto-generated surface skeleton for upstream ``core/tools/src/ts-types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/tools/src/ts-types.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "ToolSdkSchema",
    "jsonSchemaToTs",
    "renderToolsSdk",
]

def jsonSchemaToTs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``jsonSchemaToTs``."""
    raise NotImplementedError("port jsonSchemaToTs from core/tools/src/ts-types.ts")

def renderToolsSdk(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderToolsSdk``."""
    raise NotImplementedError("port renderToolsSdk from core/tools/src/ts-types.ts")

class ToolSdkSchema(Protocol):
    """Surface stub for upstream interface ``ToolSdkSchema``."""
    pass
