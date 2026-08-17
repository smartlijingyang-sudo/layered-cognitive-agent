"""Auto-generated surface skeleton for upstream ``client/ui-conversation/src/client/input/facade.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-conversation/src/client/input/facade.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PopupDismissFace",
    "SessionInputDeps",
    "SessionInputShell",
]

class SessionInputShell:
    """Surface stub for upstream class ``SessionInputShell``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionInputShell.__init__ from client/ui-conversation/src/client/input/facade.ts")

class PopupDismissFace(Protocol):
    """Surface stub for upstream interface ``PopupDismissFace``."""
    pass

class SessionInputDeps(Protocol):
    """Surface stub for upstream interface ``SessionInputDeps``."""
    pass
