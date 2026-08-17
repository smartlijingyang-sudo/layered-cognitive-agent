"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/fetch/client.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/fetch/client.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AbstractApiClient",
    "IApiClient",
    "InProcessApiClient",
]

class AbstractApiClient:
    """Surface stub for upstream class ``AbstractApiClient``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port AbstractApiClient.__init__ from host/apiproxy/src/fetch/client.ts")

class InProcessApiClient:
    """Surface stub for upstream class ``InProcessApiClient``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port InProcessApiClient.__init__ from host/apiproxy/src/fetch/client.ts")

class IApiClient(Protocol):
    """Surface stub for upstream interface ``IApiClient``."""
    pass
