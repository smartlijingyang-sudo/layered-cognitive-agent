"""Auto-generated surface skeleton for upstream ``storage/storage-domain/src/events.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-domain/src/events.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DomainChanged",
    "DomainChangedBase",
    "DomainChangedDeleted",
    "DomainChangedPut",
]

DomainChanged: TypeAlias = object  # port: surface stub

class DomainChangedBase(Protocol):
    """Surface stub for upstream interface ``DomainChangedBase``."""
    pass

class DomainChangedDeleted(Protocol):
    """Surface stub for upstream interface ``DomainChangedDeleted``."""
    pass

class DomainChangedPut(Protocol):
    """Surface stub for upstream interface ``DomainChangedPut``."""
    pass
