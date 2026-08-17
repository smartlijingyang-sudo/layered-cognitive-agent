"""Auto-generated surface skeleton for upstream ``workspace/workspace/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workspace/workspace/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Workspace",
    "WorkspaceDomainState",
    "WorkspaceId",
    "WorkspaceMoveInvalidError",
    "WorkspaceOrderInvalidError",
    "WorkspaceRecord",
    "WorkspaceRegistry",
    "WorkspaceUnknownSessionError",
    "realpathNormalize",
    "workspaceDomainSpec",
    "workspaceDomainState",
    "workspaceRecord",
]

Workspace: TypeAlias = object  # port: surface stub

WorkspaceDomainState: TypeAlias = object  # port: surface stub

WorkspaceId: TypeAlias = object  # port: surface stub

WorkspaceRecord: TypeAlias = object  # port: surface stub

class WorkspaceOrderInvalidError:
    """Surface stub for upstream class ``WorkspaceOrderInvalidError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceOrderInvalidError.__init__ from workspace/workspace/src/index.ts")

class WorkspaceRegistry:
    """Surface stub for upstream class ``WorkspaceRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceRegistry.__init__ from workspace/workspace/src/index.ts")

class WorkspaceUnknownSessionError:
    """Surface stub for upstream class ``WorkspaceUnknownSessionError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceUnknownSessionError.__init__ from workspace/workspace/src/index.ts")

WorkspaceMoveInvalidError = None  # port: surface stub (reexport)

realpathNormalize = None  # port: surface stub (reexport)

workspaceDomainSpec = None  # port: surface stub (reexport)

workspaceDomainState = None  # port: surface stub (reexport)

workspaceRecord = None  # port: surface stub (reexport)
