"""Auto-generated surface skeleton for upstream ``sdk/server/src/server.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/server/src/server.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "HarnessSdkJsonRpcServer",
    "HarnessSdkJsonRpcServerOptions",
]

class HarnessSdkJsonRpcServer:
    """Surface stub for upstream class ``HarnessSdkJsonRpcServer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port HarnessSdkJsonRpcServer.__init__ from sdk/server/src/server.ts")

class HarnessSdkJsonRpcServerOptions(Protocol):
    """Surface stub for upstream interface ``HarnessSdkJsonRpcServerOptions``."""
    pass
