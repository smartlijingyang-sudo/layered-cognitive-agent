"""Auto-generated surface skeleton for upstream ``session/session-projection/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-projection/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ProjectionChangeListener",
    "ProjectionCheckpoint",
    "ProjectionCheckpointRow",
    "ProjectionDefinition",
    "ProjectionSnapshot",
    "SessionProjectionMap",
    "SessionProjectionRegistry",
]

ProjectionChangeListener: TypeAlias = object  # port: surface stub

ProjectionCheckpoint: TypeAlias = object  # port: surface stub

SessionProjectionMap: TypeAlias = object  # port: surface stub

class SessionProjectionRegistry:
    """Surface stub for upstream class ``SessionProjectionRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionProjectionRegistry.__init__ from session/session-projection/src/index.ts")

class ProjectionCheckpointRow(Protocol):
    """Surface stub for upstream interface ``ProjectionCheckpointRow``."""
    pass

class ProjectionDefinition(Protocol):
    """Surface stub for upstream interface ``ProjectionDefinition``."""
    pass

class ProjectionSnapshot(Protocol):
    """Surface stub for upstream interface ``ProjectionSnapshot``."""
    pass
