"""Auto-generated surface skeleton for upstream ``client/ui-layout/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-layout/src/client/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ConvOwnerProps",
    "DetailsOwnerProps",
    "ILayout",
    "LayoutController",
    "SidebarOwnerProps",
    "apply",
    "inject",
]

ILayout: TypeAlias = object  # port: surface stub

inject = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/ui-layout/src/client/index.ts")

LayoutController = None  # port: surface stub (reexport)

class ConvOwnerProps(Protocol):
    """Surface stub for upstream interface ``ConvOwnerProps``."""
    pass

class DetailsOwnerProps(Protocol):
    """Surface stub for upstream interface ``DetailsOwnerProps``."""
    pass

class SidebarOwnerProps(Protocol):
    """Surface stub for upstream interface ``SidebarOwnerProps``."""
    pass
