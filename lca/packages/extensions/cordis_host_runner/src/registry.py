"""Auto-generated surface skeleton for upstream ``extensions/cordis-host-runner/src/registry.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``extensions/cordis-host-runner/src/registry.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DynamicCordisDefineReceipt",
    "DynamicCordisDefineRequest",
    "DynamicCordisDefinition",
    "DynamicCordisHandler",
    "DynamicCordisPackageInspection",
    "DynamicCordisPendingRequest",
    "DynamicCordisPlugin",
    "DynamicCordisPluginInspection",
    "DynamicCordisReference",
    "DynamicCordisRegistry",
    "DynamicCordisRun",
]

DynamicCordisHandler: TypeAlias = object  # port: surface stub

class DynamicCordisRegistry:
    """Surface stub for upstream class ``DynamicCordisRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DynamicCordisRegistry.__init__ from extensions/cordis-host-runner/src/registry.ts")

class DynamicCordisDefineReceipt(Protocol):
    """Surface stub for upstream interface ``DynamicCordisDefineReceipt``."""
    pass

class DynamicCordisDefineRequest(Protocol):
    """Surface stub for upstream interface ``DynamicCordisDefineRequest``."""
    pass

class DynamicCordisDefinition(Protocol):
    """Surface stub for upstream interface ``DynamicCordisDefinition``."""
    pass

class DynamicCordisPackageInspection(Protocol):
    """Surface stub for upstream interface ``DynamicCordisPackageInspection``."""
    pass

class DynamicCordisPendingRequest(Protocol):
    """Surface stub for upstream interface ``DynamicCordisPendingRequest``."""
    pass

class DynamicCordisPlugin(Protocol):
    """Surface stub for upstream interface ``DynamicCordisPlugin``."""
    pass

class DynamicCordisPluginInspection(Protocol):
    """Surface stub for upstream interface ``DynamicCordisPluginInspection``."""
    pass

class DynamicCordisReference(Protocol):
    """Surface stub for upstream interface ``DynamicCordisReference``."""
    pass

class DynamicCordisRun(Protocol):
    """Surface stub for upstream interface ``DynamicCordisRun``."""
    pass
