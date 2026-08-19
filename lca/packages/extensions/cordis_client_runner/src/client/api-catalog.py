"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/api-catalog.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/api-catalog.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "EVENT_API",
    "INHERITED_CTX_API",
    "SERVICE_API",
    "TYPE_API",
    "ApiParameter",
    "EventApiEntry",
    "InheritedApiEntry",
    "ServiceApiEntry",
    "ServiceApiMethod",
    "TypeApiEntry",
    "queryEventApi",
    "queryServiceApi",
]

EVENT_API = None  # port: surface stub

INHERITED_CTX_API = None  # port: surface stub

SERVICE_API = None  # port: surface stub

TYPE_API = None  # port: surface stub

def queryEventApi(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``queryEventApi``."""
    raise NotImplementedError("port queryEventApi from extensions/cordis-client-runner/src/client/api-catalog.ts")

def queryServiceApi(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``queryServiceApi``."""
    raise NotImplementedError("port queryServiceApi from extensions/cordis-client-runner/src/client/api-catalog.ts")

class ApiParameter(Protocol):
    """Surface stub for upstream interface ``ApiParameter``."""
    pass

class EventApiEntry(Protocol):
    """Surface stub for upstream interface ``EventApiEntry``."""
    pass

class InheritedApiEntry(Protocol):
    """Surface stub for upstream interface ``InheritedApiEntry``."""
    pass

class ServiceApiEntry(Protocol):
    """Surface stub for upstream interface ``ServiceApiEntry``."""
    pass

class ServiceApiMethod(Protocol):
    """Surface stub for upstream interface ``ServiceApiMethod``."""
    pass

class TypeApiEntry(Protocol):
    """Surface stub for upstream interface ``TypeApiEntry``."""
    pass
