"""Auto-generated surface skeleton for upstream ``api/gateway/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``api/gateway/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "InvokeRemoteRequest",
    "TypertGateway",
    "TypertGatewayErrorCode",
]

TypertGatewayErrorCode: TypeAlias = object  # port: surface stub

class InvokeRemoteRequest(Protocol):
    """Surface stub for upstream interface ``InvokeRemoteRequest``."""
    pass

class TypertGateway(Protocol):
    """Surface stub for upstream interface ``TypertGateway``."""
    pass
