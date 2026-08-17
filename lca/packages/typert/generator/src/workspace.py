"""Auto-generated surface skeleton for upstream ``typert/generator/src/workspace.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/generator/src/workspace.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WorkspaceEmitResult",
    "WorkspaceTypertGenerator",
]

class WorkspaceTypertGenerator:
    """Surface stub for upstream class ``WorkspaceTypertGenerator``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceTypertGenerator.__init__ from typert/generator/src/workspace.ts")

class WorkspaceEmitResult(Protocol):
    """Surface stub for upstream interface ``WorkspaceEmitResult``."""
    pass
