"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api-proxy.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api-proxy.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DEFAULT_COLD_BLANK_PROBE_MAX_BYTES",
    "ApiProxyDefaults",
    "assertJsonArgs",
    "createApiProxy",
]

DEFAULT_COLD_BLANK_PROBE_MAX_BYTES = None  # port: surface stub

def assertJsonArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertJsonArgs``."""
    raise NotImplementedError("port assertJsonArgs from host/apiproxy/src/api-proxy.ts")

def createApiProxy(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createApiProxy``."""
    raise NotImplementedError("port createApiProxy from host/apiproxy/src/api-proxy.ts")

class ApiProxyDefaults(Protocol):
    """Surface stub for upstream interface ``ApiProxyDefaults``."""
    pass
