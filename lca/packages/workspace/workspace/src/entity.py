"""Auto-generated surface skeleton for upstream ``workspace/workspace/src/entity.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workspace/workspace/src/entity.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "WorkspaceEntity",
    "WorkspaceEntityHost",
    "WorkspaceMoveInvalidError",
]

class WorkspaceEntity:
    """Surface stub for upstream class ``WorkspaceEntity``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceEntity.__init__ from workspace/workspace/src/entity.ts")

class WorkspaceMoveInvalidError:
    """Surface stub for upstream class ``WorkspaceMoveInvalidError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceMoveInvalidError.__init__ from workspace/workspace/src/entity.ts")

class WorkspaceEntityHost(Protocol):
    """Surface stub for upstream interface ``WorkspaceEntityHost``."""
    pass
