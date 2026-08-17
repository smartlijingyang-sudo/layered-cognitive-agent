"""Auto-generated surface skeleton for upstream ``client/ui-workspace/src/client/tree.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-workspace/src/client/tree.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "GroupNode",
    "RelativeTime",
    "RelativeTimeUnit",
    "SearchResultNode",
    "SearchResultSet",
    "SessionNode",
    "SessionOrderBy",
    "TreeView",
    "UNGROUPED_KEY",
    "UNGROUPED_LABEL",
    "deriveFlat",
    "deriveGroups",
    "deriveSearchResults",
    "relativeTime",
    "workspaceLabel",
]

RelativeTimeUnit: TypeAlias = object  # port: surface stub

SessionOrderBy: TypeAlias = object  # port: surface stub

UNGROUPED_KEY = None  # port: surface stub

UNGROUPED_LABEL = None  # port: surface stub

def deriveFlat(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveFlat``."""
    raise NotImplementedError("port deriveFlat from client/ui-workspace/src/client/tree.ts")

def deriveGroups(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveGroups``."""
    raise NotImplementedError("port deriveGroups from client/ui-workspace/src/client/tree.ts")

def deriveSearchResults(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveSearchResults``."""
    raise NotImplementedError("port deriveSearchResults from client/ui-workspace/src/client/tree.ts")

def relativeTime(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``relativeTime``."""
    raise NotImplementedError("port relativeTime from client/ui-workspace/src/client/tree.ts")

def workspaceLabel(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``workspaceLabel``."""
    raise NotImplementedError("port workspaceLabel from client/ui-workspace/src/client/tree.ts")

class GroupNode(Protocol):
    """Surface stub for upstream interface ``GroupNode``."""
    pass

class RelativeTime(Protocol):
    """Surface stub for upstream interface ``RelativeTime``."""
    pass

class SearchResultNode(Protocol):
    """Surface stub for upstream interface ``SearchResultNode``."""
    pass

class SearchResultSet(Protocol):
    """Surface stub for upstream interface ``SearchResultSet``."""
    pass

class SessionNode(Protocol):
    """Surface stub for upstream interface ``SessionNode``."""
    pass

class TreeView(Protocol):
    """Surface stub for upstream interface ``TreeView``."""
    pass
