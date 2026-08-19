"""Auto-generated surface skeleton for upstream ``client/ui-input-trigger/src/core/contract.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-input-trigger/src/core/contract.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DetectTrigger",
    "ExactMatch",
    "MenuEvent",
    "MenuReduce",
    "MenuState",
    "TriggerHit",
]

DetectTrigger: TypeAlias = object  # port: surface stub

ExactMatch: TypeAlias = object  # port: surface stub

MenuEvent: TypeAlias = object  # port: surface stub

MenuReduce: TypeAlias = object  # port: surface stub

class MenuState(Protocol):
    """Surface stub for upstream interface ``MenuState``."""
    pass

class TriggerHit(Protocol):
    """Surface stub for upstream interface ``TriggerHit``."""
    pass
