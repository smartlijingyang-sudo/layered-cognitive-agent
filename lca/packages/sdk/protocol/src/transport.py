"""Auto-generated surface skeleton for upstream ``sdk/protocol/src/transport.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/protocol/src/transport.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "JsonRpcLineTransport",
    "JsonRpcResponseError",
    "JsonRpcTransportPeer",
]

class JsonRpcLineTransport:
    """Surface stub for upstream class ``JsonRpcLineTransport``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port JsonRpcLineTransport.__init__ from sdk/protocol/src/transport.ts")

class JsonRpcResponseError:
    """Surface stub for upstream class ``JsonRpcResponseError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port JsonRpcResponseError.__init__ from sdk/protocol/src/transport.ts")

class JsonRpcTransportPeer(Protocol):
    """Surface stub for upstream interface ``JsonRpcTransportPeer``."""
    pass
