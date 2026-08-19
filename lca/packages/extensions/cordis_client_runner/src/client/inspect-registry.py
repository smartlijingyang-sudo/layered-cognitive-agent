"""Auto-generated surface skeleton for upstream ``extensions/cordis-client-runner/src/client/inspect-registry.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-client-runner/src/client/inspect-registry.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "ClientCordisInspectHost",
    "ClientCordisInspectProviderRegistration",
    "ClientCordisInspectQueryContext",
    "ClientCordisInspectRegistry",
    "provideClientCordisInspect",
]

def provideClientCordisInspect(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``provideClientCordisInspect``."""
    raise NotImplementedError("port provideClientCordisInspect from extensions/cordis-client-runner/src/client/inspect-registry.ts")

class ClientCordisInspectRegistry:
    """Surface stub for upstream class ``ClientCordisInspectRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ClientCordisInspectRegistry.__init__ from extensions/cordis-client-runner/src/client/inspect-registry.ts")

class ClientCordisInspectHost(Protocol):
    """Surface stub for upstream interface ``ClientCordisInspectHost``."""
    pass

class ClientCordisInspectProviderRegistration(Protocol):
    """Surface stub for upstream interface ``ClientCordisInspectProviderRegistration``."""
    pass

class ClientCordisInspectQueryContext(Protocol):
    """Surface stub for upstream interface ``ClientCordisInspectQueryContext``."""
    pass
