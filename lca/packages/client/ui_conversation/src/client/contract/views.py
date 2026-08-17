"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/contract/views.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/contract/views.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CallId",
    "ChatStoreState",
    "SelectionTarget",
    "ViewTab",
]

CallId: TypeAlias = object  # port: surface stub

class ChatStoreState(Protocol):
    """Surface stub for upstream interface ``ChatStoreState``."""
    pass

class SelectionTarget(Protocol):
    """Surface stub for upstream interface ``SelectionTarget``."""
    pass

class ViewTab(Protocol):
    """Surface stub for upstream interface ``ViewTab``."""
    pass
