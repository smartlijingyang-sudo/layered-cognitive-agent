"""Auto-generated surface skeleton for upstream ``client/modules/src/client/manifest.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/modules/src/client/manifest.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "BootManifest",
    "BootModuleRow",
    "BootPluginRow",
    "ClientModuleLoader",
    "ClientModuleRecord",
    "ClientModuleSystemOptions",
    "ClientPluginHandoff",
    "DshWindow",
    "WebBootEntry",
    "WebBootGraph",
    "parseBootManifest",
]

def parseBootManifest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseBootManifest``."""
    raise NotImplementedError("port parseBootManifest from client/modules/src/client/manifest.ts")

class BootManifest(Protocol):
    """Surface stub for upstream interface ``BootManifest``."""
    pass

class BootModuleRow(Protocol):
    """Surface stub for upstream interface ``BootModuleRow``."""
    pass

class BootPluginRow(Protocol):
    """Surface stub for upstream interface ``BootPluginRow``."""
    pass

class ClientModuleLoader(Protocol):
    """Surface stub for upstream interface ``ClientModuleLoader``."""
    pass

class ClientModuleRecord(Protocol):
    """Surface stub for upstream interface ``ClientModuleRecord``."""
    pass

class ClientModuleSystemOptions(Protocol):
    """Surface stub for upstream interface ``ClientModuleSystemOptions``."""
    pass

class ClientPluginHandoff(Protocol):
    """Surface stub for upstream interface ``ClientPluginHandoff``."""
    pass

class DshWindow(Protocol):
    """Surface stub for upstream interface ``DshWindow``."""
    pass

class WebBootEntry(Protocol):
    """Surface stub for upstream interface ``WebBootEntry``."""
    pass

class WebBootGraph(Protocol):
    """Surface stub for upstream interface ``WebBootGraph``."""
    pass
