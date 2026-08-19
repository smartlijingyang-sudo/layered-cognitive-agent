"""Auto-generated surface skeleton for upstream ``client/connection/src/client/connection.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/connection/src/client/connection.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ConnectionConfig",
    "ConnectionController",
    "ConnectionSinks",
    "ConnectionState",
]

ConnectionState: TypeAlias = object  # port: surface stub

class ConnectionController:
    """Surface stub for upstream class ``ConnectionController``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ConnectionController.__init__ from client/connection/src/client/connection.ts")

class ConnectionConfig(Protocol):
    """Surface stub for upstream interface ``ConnectionConfig``."""
    pass

class ConnectionSinks(Protocol):
    """Surface stub for upstream interface ``ConnectionSinks``."""
    pass
