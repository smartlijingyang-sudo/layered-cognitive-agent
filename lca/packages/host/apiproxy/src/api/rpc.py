"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/rpc.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/rpc.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ClientRequest",
    "ClientResponse",
    "RpcError",
    "RpcErrorCode",
    "RpcErrorDetailsMap",
    "RpcId",
    "RpcMessage",
    "RpcReceipt",
    "RpcRequest",
    "RpcResponse",
    "RpcResult",
    "ServerRequest",
    "ServerResponse",
    "transportError",
]

RpcError: TypeAlias = object  # port: surface stub

RpcErrorCode: TypeAlias = object  # port: surface stub

RpcId: TypeAlias = object  # port: surface stub

RpcMessage: TypeAlias = object  # port: surface stub

RpcReceipt: TypeAlias = object  # port: surface stub

RpcResult: TypeAlias = object  # port: surface stub

def transportError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``transportError``."""
    raise NotImplementedError("port transportError from host/apiproxy/src/api/rpc.ts")

class ClientRequest(Protocol):
    """Surface stub for upstream interface ``ClientRequest``."""
    pass

class ClientResponse(Protocol):
    """Surface stub for upstream interface ``ClientResponse``."""
    pass

class RpcErrorDetailsMap(Protocol):
    """Surface stub for upstream interface ``RpcErrorDetailsMap``."""
    pass

class RpcRequest(Protocol):
    """Surface stub for upstream interface ``RpcRequest``."""
    pass

class RpcResponse(Protocol):
    """Surface stub for upstream interface ``RpcResponse``."""
    pass

class ServerRequest(Protocol):
    """Surface stub for upstream interface ``ServerRequest``."""
    pass

class ServerResponse(Protocol):
    """Surface stub for upstream interface ``ServerResponse``."""
    pass
