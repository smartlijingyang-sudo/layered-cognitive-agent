"""Auto-generated surface skeleton for upstream ``host/directory-picker-native/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-native/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "DirectoryPickerInternals",
    "DirectoryPickerRunner",
    "NativeDirectoryPicker",
    "pickNativeDirectory",
]

DirectoryPickerInternals: TypeAlias = object  # port: surface stub

DirectoryPickerRunner: TypeAlias = object  # port: surface stub

class NativeDirectoryPicker:
    """Surface stub for upstream class ``NativeDirectoryPicker``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port NativeDirectoryPicker.__init__ from host/directory-picker-native/src/index.ts")

pickNativeDirectory = None  # port: surface stub (reexport)
