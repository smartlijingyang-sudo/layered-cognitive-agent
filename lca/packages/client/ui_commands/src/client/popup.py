"""Auto-generated surface skeleton for upstream ``client/ui-commands/src/client/popup.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-commands/src/client/popup.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PopupSelectController",
    "PopupSelectDeps",
    "PopupSpec",
    "PopupState",
    "TokenSegment",
    "filterOptions",
]

TokenSegment: TypeAlias = object  # port: surface stub

def filterOptions(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``filterOptions``."""
    raise NotImplementedError("port filterOptions from client/ui-commands/src/client/popup.ts")

class PopupSelectController:
    """Surface stub for upstream class ``PopupSelectController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port PopupSelectController.__init__ from client/ui-commands/src/client/popup.ts")

class PopupSelectDeps(Protocol):
    """Surface stub for upstream interface ``PopupSelectDeps``."""
    pass

class PopupSpec(Protocol):
    """Surface stub for upstream interface ``PopupSpec``."""
    pass

class PopupState(Protocol):
    """Surface stub for upstream interface ``PopupState``."""
    pass
