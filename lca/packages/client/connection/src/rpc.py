"""Auto-generated surface skeleton for upstream ``client/connection/src/rpc.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/connection/src/rpc.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ClientConnectionRpc",
    "ConnectionRpcAuthority",
    "ConnectionRpcEndpointMatcher",
    "ConnectionRpcHandler",
    "ConnectionRpcHandlerOptions",
    "HostConnectionHandle",
    "HostConnectionRpc",
]

ConnectionRpcAuthority: TypeAlias = object  # port: surface stub

ConnectionRpcEndpointMatcher: TypeAlias = object  # port: surface stub

ConnectionRpcHandler: TypeAlias = object  # port: surface stub

class ClientConnectionRpc(Protocol):
    """Surface stub for upstream interface ``ClientConnectionRpc``."""
    pass

class ConnectionRpcHandlerOptions(Protocol):
    """Surface stub for upstream interface ``ConnectionRpcHandlerOptions``."""
    pass

class HostConnectionHandle(Protocol):
    """Surface stub for upstream interface ``HostConnectionHandle``."""
    pass

class HostConnectionRpc(Protocol):
    """Surface stub for upstream interface ``HostConnectionRpc``."""
    pass
