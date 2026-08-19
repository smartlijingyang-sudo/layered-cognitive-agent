"""Auto-generated surface skeleton for upstream ``core/session/src/preparation.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/session/src/preparation.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SessionPreparation",
    "SessionPreparationOptions",
]

class SessionPreparation:
    """Surface stub for upstream class ``SessionPreparation``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionPreparation.__init__ from core/session/src/preparation.ts")

class SessionPreparationOptions(Protocol):
    """Surface stub for upstream interface ``SessionPreparationOptions``."""
    pass
