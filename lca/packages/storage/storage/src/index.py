"""Auto-generated surface skeleton for upstream ``storage/storage/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``storage/storage/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BackendRegistry",
    "KvFacet",
    "KvUnit",
    "KvUnitDescriptor",
    "Storage",
    "StorageBackend",
    "StorageError",
    "StorageErrorCode",
    "StorageForms",
    "UNIT_NAME_RE",
    "storageBackendServiceKey",
]

KvFacet: TypeAlias = object  # port: surface stub

KvUnit: TypeAlias = object  # port: surface stub

KvUnitDescriptor: TypeAlias = object  # port: surface stub

StorageBackend: TypeAlias = object  # port: surface stub

StorageErrorCode: TypeAlias = object  # port: surface stub

def storageBackendServiceKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``storageBackendServiceKey``."""
    raise NotImplementedError("port storageBackendServiceKey from storage/storage/src/index.ts")

class Storage:
    """Surface stub for upstream class ``Storage``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port Storage.__init__ from storage/storage/src/index.ts")

BackendRegistry = None  # port: surface stub (reexport)

StorageError = None  # port: surface stub (reexport)

UNIT_NAME_RE = None  # port: surface stub (reexport)

class StorageForms(Protocol):
    """Surface stub for upstream interface ``StorageForms``."""
    pass
