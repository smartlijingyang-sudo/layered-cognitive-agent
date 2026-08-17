"""Auto-generated surface skeleton for upstream ``client/connection/src/http-bridge.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/connection/src/http-bridge.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_MAX_REQUEST_BODY_BYTES",
    "FetchHandler",
    "bridge",
]

DEFAULT_MAX_REQUEST_BODY_BYTES = None  # port: surface stub

def bridge(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``bridge``."""
    raise NotImplementedError("port bridge from client/connection/src/http-bridge.ts")

class FetchHandler(Protocol):
    """Surface stub for upstream interface ``FetchHandler``."""
    pass
