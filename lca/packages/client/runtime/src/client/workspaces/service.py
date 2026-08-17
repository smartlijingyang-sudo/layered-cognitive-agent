"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/workspaces/service.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/workspaces/service.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DirectoryBrowseError",
    "WorkspaceCreateError",
    "WorkspaceListState",
    "WorkspaceRuntime",
]

class DirectoryBrowseError:
    """Surface stub for upstream class ``DirectoryBrowseError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DirectoryBrowseError.__init__ from client/runtime/src/client/workspaces/service.ts")

class WorkspaceCreateError:
    """Surface stub for upstream class ``WorkspaceCreateError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceCreateError.__init__ from client/runtime/src/client/workspaces/service.ts")

class WorkspaceRuntime:
    """Surface stub for upstream class ``WorkspaceRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceRuntime.__init__ from client/runtime/src/client/workspaces/service.ts")

class WorkspaceListState(Protocol):
    """Surface stub for upstream interface ``WorkspaceListState``."""
    pass
