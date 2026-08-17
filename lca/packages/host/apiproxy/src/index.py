"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AbstractApiClient",
    "ApiProxyDefaults",
    "ApiProxyService",
    "Config",
    "IApiClient",
    "InProcessApiClient",
    "RpcId",
    "createApiProxy",
    "toFetchHandler",
]

ApiProxyDefaults: TypeAlias = object  # port: surface stub

IApiClient: TypeAlias = object  # port: surface stub

class ApiProxyService:
    """Surface stub for upstream class ``ApiProxyService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ApiProxyService.__init__ from host/apiproxy/src/index.ts")

AbstractApiClient = None  # port: surface stub (reexport)

InProcessApiClient = None  # port: surface stub (reexport)

RpcId = None  # port: surface stub (reexport)

createApiProxy = None  # port: surface stub (reexport)

toFetchHandler = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
