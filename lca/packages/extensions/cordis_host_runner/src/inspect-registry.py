"""Auto-generated surface skeleton for upstream ``extensions/cordis-host-runner/src/inspect-registry.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-host-runner/src/inspect-registry.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CordisInspectRegistryService",
    "HostCordisInspectProviderRegistration",
    "HostCordisInspectQueryContext",
]

class CordisInspectRegistryService:
    """Surface stub for upstream class ``CordisInspectRegistryService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port CordisInspectRegistryService.__init__ from extensions/cordis-host-runner/src/inspect-registry.ts")

class HostCordisInspectProviderRegistration(Protocol):
    """Surface stub for upstream interface ``HostCordisInspectProviderRegistration``."""
    pass

class HostCordisInspectQueryContext(Protocol):
    """Surface stub for upstream interface ``HostCordisInspectQueryContext``."""
    pass
