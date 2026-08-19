"""Auto-generated surface skeleton for upstream ``api/gateway/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``api/gateway/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "InvokeRemoteRequest",
    "TypertGateway",
    "TypertGatewayError",
    "TypertGatewayErrorCode",
    "TypertGatewayService",
]

InvokeRemoteRequest: TypeAlias = object  # port: surface stub

TypertGateway: TypeAlias = object  # port: surface stub

TypertGatewayErrorCode: TypeAlias = object  # port: surface stub

class TypertGatewayError:
    """Surface stub for upstream class ``TypertGatewayError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TypertGatewayError.__init__ from api/gateway/src/index.ts")

class TypertGatewayService:
    """Surface stub for upstream class ``TypertGatewayService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TypertGatewayService.__init__ from api/gateway/src/index.ts")
