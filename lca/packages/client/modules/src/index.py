"""Auto-generated surface skeleton for upstream ``client/modules/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/modules/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "BootManifest",
    "BootModuleRow",
    "BootPluginRow",
    "ClientModuleRegistry",
    "WebBootEntry",
    "WebBootGraph",
    "injectBootManifest",
]

BootManifest: TypeAlias = object  # port: surface stub

BootModuleRow: TypeAlias = object  # port: surface stub

BootPluginRow: TypeAlias = object  # port: surface stub

WebBootEntry: TypeAlias = object  # port: surface stub

WebBootGraph: TypeAlias = object  # port: surface stub

def injectBootManifest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``injectBootManifest``."""
    raise NotImplementedError("port injectBootManifest from client/modules/src/index.ts")

class ClientModuleRegistry:
    """Surface stub for upstream class ``ClientModuleRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ClientModuleRegistry.__init__ from client/modules/src/index.ts")
