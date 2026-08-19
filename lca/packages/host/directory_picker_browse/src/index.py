"""Auto-generated surface skeleton for upstream ``host/directory-picker-browse/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/directory-picker-browse/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "BrowseDirectoryPicker",
    "Config",
    "ListingCandidate",
    "boundedInsert",
    "fullyQualified",
    "raceAbort",
]

def boundedInsert(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``boundedInsert``."""
    raise NotImplementedError("port boundedInsert from host/directory-picker-browse/src/index.ts")

def fullyQualified(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``fullyQualified``."""
    raise NotImplementedError("port fullyQualified from host/directory-picker-browse/src/index.ts")

def raceAbort(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``raceAbort``."""
    raise NotImplementedError("port raceAbort from host/directory-picker-browse/src/index.ts")

class BrowseDirectoryPicker:
    """Surface stub for upstream class ``BrowseDirectoryPicker``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port BrowseDirectoryPicker.__init__ from host/directory-picker-browse/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class ListingCandidate(Protocol):
    """Surface stub for upstream interface ``ListingCandidate``."""
    pass
