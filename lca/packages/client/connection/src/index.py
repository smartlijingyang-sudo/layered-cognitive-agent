"""Auto-generated surface skeleton for upstream ``client/connection/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/connection/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "API_PATH",
    "HOST_EVENTS_PATH",
    "MUX_EVENTS_PATH",
    "Config",
    "ConnectionConfig",
    "ConnectionRpcAuthority",
    "ConnectionRpcEndpointMatcher",
    "ConnectionRpcHandler",
    "ConnectionRpcHandlerOptions",
    "HostConnectionHandle",
    "HostConnectionRpc",
    "HostConnectionService",
    "apply",
    "inject",
    "name",
]

ConnectionRpcAuthority: TypeAlias = object  # port: surface stub

ConnectionRpcEndpointMatcher: TypeAlias = object  # port: surface stub

ConnectionRpcHandler: TypeAlias = object  # port: surface stub

ConnectionRpcHandlerOptions: TypeAlias = object  # port: surface stub

HostConnectionHandle: TypeAlias = object  # port: surface stub

HostConnectionRpc: TypeAlias = object  # port: surface stub

Config = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/connection/src/index.ts")

API_PATH = None  # port: surface stub (reexport)

HOST_EVENTS_PATH = None  # port: surface stub (reexport)

HostConnectionService = None  # port: surface stub (reexport)

MUX_EVENTS_PATH = None  # port: surface stub (reexport)

class ConnectionConfig(Protocol):
    """Surface stub for upstream interface ``ConnectionConfig``."""
    pass
