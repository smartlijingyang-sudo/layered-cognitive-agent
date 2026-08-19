"""Auto-generated surface skeleton for upstream ``host/directory-picker-native/src/native-picker.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-native/src/native-picker.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DirectoryPickerInternals",
    "DirectoryPickerRunner",
    "pickNativeDirectory",
]

DirectoryPickerRunner: TypeAlias = object  # port: surface stub

def pickNativeDirectory(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``pickNativeDirectory``."""
    raise NotImplementedError("port pickNativeDirectory from host/directory-picker-native/src/native-picker.ts")

class DirectoryPickerInternals(Protocol):
    """Surface stub for upstream interface ``DirectoryPickerInternals``."""
    pass
