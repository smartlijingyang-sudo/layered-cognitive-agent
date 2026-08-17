"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/slots.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/slots.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RootOwnerProps",
    "SlotRegistry",
]

class SlotRegistry:
    """Surface stub for upstream class ``SlotRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SlotRegistry.__init__ from client/runtime/src/client/slots.ts")

class RootOwnerProps(Protocol):
    """Surface stub for upstream interface ``RootOwnerProps``."""
    pass
