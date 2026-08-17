"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/provide.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/provide.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SessionProvideChannel",
    "SessionProvideChannelHost",
]

class SessionProvideChannel:
    """Surface stub for upstream class ``SessionProvideChannel``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionProvideChannel.__init__ from client/runtime/src/client/sessions/provide.ts")

class SessionProvideChannelHost(Protocol):
    """Surface stub for upstream interface ``SessionProvideChannelHost``."""
    pass
