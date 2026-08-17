"""Auto-generated surface skeleton for upstream ``core/session/src/chunk-rows.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/session/src/chunk-rows.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ChunkRow",
    "StorageRecord",
    "decodeStorageRecord",
    "packChunkRuns",
]

ChunkRow: TypeAlias = object  # port: surface stub

StorageRecord: TypeAlias = object  # port: surface stub

def decodeStorageRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeStorageRecord``."""
    raise NotImplementedError("port decodeStorageRecord from core/session/src/chunk-rows.ts")

def packChunkRuns(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``packChunkRuns``."""
    raise NotImplementedError("port packChunkRuns from core/session/src/chunk-rows.ts")
