"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/contract/store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/contract/store.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ActionsDecl",
    "BakedActions",
    "BoundActions",
    "EngineStoreHandle",
    "EngineStoreInstance",
    "ObservableSnapshot",
    "SnapshotStore",
    "StoreFactory",
    "StoreHandle",
    "StoreInstance",
    "StoreSpec",
    "createSnapshotStore",
    "defineStore",
    "shallowEqual",
]

ActionsDecl: TypeAlias = object  # port: surface stub

BakedActions: TypeAlias = object  # port: surface stub

BoundActions: TypeAlias = object  # port: surface stub

StoreFactory: TypeAlias = object  # port: surface stub

StoreHandle: TypeAlias = object  # port: surface stub

StoreInstance: TypeAlias = object  # port: surface stub

StoreSpec: TypeAlias = object  # port: surface stub

def createSnapshotStore(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createSnapshotStore``."""
    raise NotImplementedError("port createSnapshotStore from client/runtime/src/client/contract/store.ts")

def defineStore(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``defineStore``."""
    raise NotImplementedError("port defineStore from client/runtime/src/client/contract/store.ts")

def shallowEqual(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``shallowEqual``."""
    raise NotImplementedError("port shallowEqual from client/runtime/src/client/contract/store.ts")

class EngineStoreHandle(Protocol):
    """Surface stub for upstream interface ``EngineStoreHandle``."""
    pass

class EngineStoreInstance(Protocol):
    """Surface stub for upstream interface ``EngineStoreInstance``."""
    pass

class ObservableSnapshot(Protocol):
    """Surface stub for upstream interface ``ObservableSnapshot``."""
    pass

class SnapshotStore(Protocol):
    """Surface stub for upstream interface ``SnapshotStore``."""
    pass
