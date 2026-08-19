"""Auto-generated surface skeleton for upstream ``host/directory-picker-auto/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-auto/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "BACKEND_PACKAGES",
    "SURFACE_PACKAGES",
    "DirectoryPickerBackendKind",
    "DirectoryPickerEnv",
    "DirectoryPickerHostFacts",
    "apply",
    "canExecute",
    "hasLinuxChooserBinary",
    "inject",
    "name",
    "resolveDirectoryPickerBackend",
]

DirectoryPickerBackendKind: TypeAlias = object  # port: surface stub

DirectoryPickerEnv: TypeAlias = object  # port: surface stub

DirectoryPickerHostFacts: TypeAlias = object  # port: surface stub

BACKEND_PACKAGES = None  # port: surface stub

SURFACE_PACKAGES = None  # port: surface stub

inject = None  # port: surface stub

name = None  # port: surface stub

def apply(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``apply``."""
    raise NotImplementedError("port apply from host/directory-picker-auto/src/index.ts")

canExecute = None  # port: surface stub (reexport)

hasLinuxChooserBinary = None  # port: surface stub (reexport)

resolveDirectoryPickerBackend = None  # port: surface stub (reexport)
