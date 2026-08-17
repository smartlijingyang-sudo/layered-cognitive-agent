"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/manager.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/manager.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SessionListPhase",
    "SessionListSnapshot",
    "SessionManager",
    "SessionSearchResultItem",
    "SubagentCatalogSnapshot",
]

SessionListPhase: TypeAlias = object  # port: surface stub

class SessionManager:
    """Surface stub for upstream class ``SessionManager``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionManager.__init__ from client/runtime/src/client/sessions/manager.ts")

class SessionListSnapshot(Protocol):
    """Surface stub for upstream interface ``SessionListSnapshot``."""
    pass

class SessionSearchResultItem(Protocol):
    """Surface stub for upstream interface ``SessionSearchResultItem``."""
    pass

class SubagentCatalogSnapshot(Protocol):
    """Surface stub for upstream interface ``SubagentCatalogSnapshot``."""
    pass
