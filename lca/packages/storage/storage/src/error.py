"""Auto-generated surface skeleton for upstream ``storage/storage/src/error.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage/src/error.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "StorageError",
    "StorageErrorCode",
]

StorageErrorCode: TypeAlias = object  # port: surface stub

class StorageError:
    """Surface stub for upstream class ``StorageError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port StorageError.__init__ from storage/storage/src/error.ts")
