"""Auto-generated surface skeleton for upstream ``client/ui-settings-plugins/src/client/bash-card-controller.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-settings-plugins/src/client/bash-card-controller.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BashCardController",
    "BashCardFace",
    "BashCardState",
    "BashSettings",
    "SHELL_NS",
]

SHELL_NS = None  # port: surface stub

class BashCardController:
    """Surface stub for upstream class ``BashCardController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port BashCardController.__init__ from client/ui-settings-plugins/src/client/bash-card-controller.ts")

class BashCardFace(Protocol):
    """Surface stub for upstream interface ``BashCardFace``."""
    pass

class BashCardState(Protocol):
    """Surface stub for upstream interface ``BashCardState``."""
    pass

class BashSettings(Protocol):
    """Surface stub for upstream interface ``BashSettings``."""
    pass
