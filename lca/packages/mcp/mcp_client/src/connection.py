"""Auto-generated surface skeleton for upstream ``mcp/mcp-client/src/connection.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``mcp/mcp-client/src/connection.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ConnectionHandle",
    "ConnectionOutcome",
    "RECONNECT_DEFAULTS",
    "ReconnectConfig",
    "ResolvedReconnectPolicy",
    "resolveReconnectPolicy",
    "startConnection",
]

ResolvedReconnectPolicy: TypeAlias = object  # port: surface stub

RECONNECT_DEFAULTS = None  # port: surface stub

def resolveReconnectPolicy(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveReconnectPolicy``."""
    raise NotImplementedError("port resolveReconnectPolicy from mcp/mcp-client/src/connection.ts")

def startConnection(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startConnection``."""
    raise NotImplementedError("port startConnection from mcp/mcp-client/src/connection.ts")

class ConnectionHandle(Protocol):
    """Surface stub for upstream interface ``ConnectionHandle``."""
    pass

class ConnectionOutcome(Protocol):
    """Surface stub for upstream interface ``ConnectionOutcome``."""
    pass

class ReconnectConfig(Protocol):
    """Surface stub for upstream interface ``ReconnectConfig``."""
    pass
