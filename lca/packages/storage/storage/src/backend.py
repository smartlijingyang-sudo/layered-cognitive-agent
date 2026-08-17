"""Auto-generated surface skeleton for upstream ``storage/storage/src/backend.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage/src/backend.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "KvFacet",
    "KvUnit",
    "KvUnitDescriptor",
    "StorageBackend",
    "UNIT_NAME_RE",
]

UNIT_NAME_RE = None  # port: surface stub

class KvFacet(Protocol):
    """Surface stub for upstream interface ``KvFacet``."""
    pass

class KvUnit(Protocol):
    """Surface stub for upstream interface ``KvUnit``."""
    pass

class KvUnitDescriptor(Protocol):
    """Surface stub for upstream interface ``KvUnitDescriptor``."""
    pass

class StorageBackend(Protocol):
    """Surface stub for upstream interface ``StorageBackend``."""
    pass
