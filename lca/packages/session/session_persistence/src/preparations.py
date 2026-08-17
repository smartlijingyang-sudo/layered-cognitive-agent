"""Auto-generated surface skeleton for upstream ``session/session-persistence/src/preparations.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence/src/preparations.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SessionPreparationReservation",
    "SessionPreparations",
    "observeQueuedAbort",
]

def observeQueuedAbort(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``observeQueuedAbort``."""
    raise NotImplementedError("port observeQueuedAbort from session/session-persistence/src/preparations.ts")

class SessionPreparations:
    """Surface stub for upstream class ``SessionPreparations``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionPreparations.__init__ from session/session-persistence/src/preparations.ts")

class SessionPreparationReservation(Protocol):
    """Surface stub for upstream interface ``SessionPreparationReservation``."""
    pass
