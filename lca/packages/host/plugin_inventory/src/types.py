"""Auto-generated surface skeleton for upstream ``host/plugin-inventory/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/plugin-inventory/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PluginEntryId",
    "PluginFiberPhase",
    "PluginInventoryEntry",
    "PluginInventorySnapshot",
]

PluginEntryId: TypeAlias = object  # port: surface stub

PluginFiberPhase: TypeAlias = object  # port: surface stub

class PluginInventoryEntry(Protocol):
    """Surface stub for upstream interface ``PluginInventoryEntry``."""
    pass

class PluginInventorySnapshot(Protocol):
    """Surface stub for upstream interface ``PluginInventorySnapshot``."""
    pass
