"""Auto-generated surface skeleton for upstream ``storage/storage-json/src/format.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage-json/src/format.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "UnitState",
    "parse",
    "serialize",
]

def parse(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parse``."""
    raise NotImplementedError("port parse from storage/storage-json/src/format.ts")

def serialize(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``serialize``."""
    raise NotImplementedError("port serialize from storage/storage-json/src/format.ts")

class UnitState(Protocol):
    """Surface stub for upstream interface ``UnitState``."""
    pass
