"""Auto-generated surface skeleton for upstream ``client/runtime/src/client/sessions/projection-store.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/runtime/src/client/sessions/projection-store.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ProjectionValueStore",
    "ProjectionsBaseline",
    "SessionProjectionMap",
    "UseProjection",
]

SessionProjectionMap: TypeAlias = object  # port: surface stub

UseProjection: TypeAlias = object  # port: surface stub

class ProjectionValueStore:
    """Surface stub for upstream class ``ProjectionValueStore``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ProjectionValueStore.__init__ from client/runtime/src/client/sessions/projection-store.ts")

class ProjectionsBaseline(Protocol):
    """Surface stub for upstream interface ``ProjectionsBaseline``."""
    pass
