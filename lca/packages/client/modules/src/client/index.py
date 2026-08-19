"""Auto-generated surface skeleton for upstream ``client/modules/src/client/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/modules/src/client/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "BootManifest",
    "BootModuleRow",
    "BootPluginRow",
    "ClientModuleLoader",
    "ClientModuleRecord",
    "ClientModuleSystem",
    "ClientModuleSystemOptions",
    "ClientPluginHandoff",
    "DshWindow",
    "WebBootEntry",
    "WebBootGraph",
    "apply",
    "parseBootManifest",
]

BootManifest: TypeAlias = object  # port: surface stub

BootModuleRow: TypeAlias = object  # port: surface stub

BootPluginRow: TypeAlias = object  # port: surface stub

ClientModuleLoader: TypeAlias = object  # port: surface stub

ClientModuleRecord: TypeAlias = object  # port: surface stub

ClientModuleSystemOptions: TypeAlias = object  # port: surface stub

ClientPluginHandoff: TypeAlias = object  # port: surface stub

DshWindow: TypeAlias = object  # port: surface stub

WebBootEntry: TypeAlias = object  # port: surface stub

WebBootGraph: TypeAlias = object  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from client/modules/src/client/index.ts")

ClientModuleSystem = None  # port: surface stub (reexport)

parseBootManifest = None  # port: surface stub (reexport)
