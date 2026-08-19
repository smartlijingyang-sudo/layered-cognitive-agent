"""Auto-generated surface skeleton for upstream ``client/ui-slots/src/store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-slots/src/store.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ActionsDecl",
    "BakedActions",
    "BoundActions",
    "DefineStore",
    "HandleOf",
    "MaybeSnapshotSelectorHook",
    "PropsStore",
    "SnapshotSelectorHook",
    "StoreDecl",
    "StoreFactory",
    "StoreHandle",
    "StoreInstance",
    "StoreSpec",
]

ActionsDecl: TypeAlias = object  # port: surface stub

BakedActions: TypeAlias = object  # port: surface stub

BoundActions: TypeAlias = object  # port: surface stub

DefineStore: TypeAlias = object  # port: surface stub

HandleOf: TypeAlias = object  # port: surface stub

MaybeSnapshotSelectorHook: TypeAlias = object  # port: surface stub

PropsStore: TypeAlias = object  # port: surface stub

SnapshotSelectorHook: TypeAlias = object  # port: surface stub

StoreDecl: TypeAlias = object  # port: surface stub

StoreFactory: TypeAlias = object  # port: surface stub

class StoreHandle(Protocol):
    """Surface stub for upstream interface ``StoreHandle``."""
    pass

class StoreInstance(Protocol):
    """Surface stub for upstream interface ``StoreInstance``."""
    pass

class StoreSpec(Protocol):
    """Surface stub for upstream interface ``StoreSpec``."""
    pass
