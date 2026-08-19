"""Auto-generated surface skeleton for upstream ``session/session-persistence/src/write-behind.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-persistence/src/write-behind.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SessionWriteBehind",
    "SessionWriteBehindOptions",
]

class SessionWriteBehind:
    """Surface stub for upstream class ``SessionWriteBehind``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionWriteBehind.__init__ from session/session-persistence/src/write-behind.ts")

class SessionWriteBehindOptions(Protocol):
    """Surface stub for upstream interface ``SessionWriteBehindOptions``."""
    pass
