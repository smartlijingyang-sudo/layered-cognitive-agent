"""Auto-generated surface skeleton for upstream ``host/directory-picker-auto/src/resolve.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-auto/src/resolve.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DirectoryPickerBackendKind",
    "DirectoryPickerEnv",
    "DirectoryPickerHostFacts",
    "resolveDirectoryPickerBackend",
]

DirectoryPickerBackendKind: TypeAlias = object  # port: surface stub

DirectoryPickerEnv: TypeAlias = object  # port: surface stub

def resolveDirectoryPickerBackend(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveDirectoryPickerBackend``."""
    raise NotImplementedError("port resolveDirectoryPickerBackend from host/directory-picker-auto/src/resolve.ts")

class DirectoryPickerHostFacts(Protocol):
    """Surface stub for upstream interface ``DirectoryPickerHostFacts``."""
    pass
