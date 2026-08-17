"""Auto-generated surface skeleton for upstream ``host/directory-picker/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DirectoryEntry",
    "DirectoryListing",
    "DirectoryPicker",
    "DirectoryPickerBrowseCapability",
    "DirectoryPickerCapabilities",
    "DirectoryPickerCapability",
    "DirectoryPickerError",
    "DirectoryPickerErrorCode",
    "DirectoryPickerNativeCapability",
]

DirectoryPickerCapability: TypeAlias = object  # port: surface stub

DirectoryPickerErrorCode: TypeAlias = object  # port: surface stub

class DirectoryPicker:
    """Surface stub for upstream class ``DirectoryPicker``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DirectoryPicker.__init__ from host/directory-picker/src/index.ts")

class DirectoryPickerError:
    """Surface stub for upstream class ``DirectoryPickerError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port DirectoryPickerError.__init__ from host/directory-picker/src/index.ts")

class DirectoryEntry(Protocol):
    """Surface stub for upstream interface ``DirectoryEntry``."""
    pass

class DirectoryListing(Protocol):
    """Surface stub for upstream interface ``DirectoryListing``."""
    pass

class DirectoryPickerBrowseCapability(Protocol):
    """Surface stub for upstream interface ``DirectoryPickerBrowseCapability``."""
    pass

class DirectoryPickerCapabilities(Protocol):
    """Surface stub for upstream interface ``DirectoryPickerCapabilities``."""
    pass

class DirectoryPickerNativeCapability(Protocol):
    """Surface stub for upstream interface ``DirectoryPickerNativeCapability``."""
    pass
