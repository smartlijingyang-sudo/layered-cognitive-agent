"""Auto-generated surface skeleton for upstream ``session/session-projection-cache/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``session/session-projection-cache/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CheckpointIdentity",
    "CheckpointRecord",
    "Config",
    "SessionProjectionCache",
    "checkpointIdentity",
    "checkpointRecord",
    "checkpointRow",
    "projectionCacheDomainSpec",
]

CheckpointIdentity: TypeAlias = object  # port: surface stub

CheckpointRecord: TypeAlias = object  # port: surface stub

class SessionProjectionCache:
    """Surface stub for upstream class ``SessionProjectionCache``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SessionProjectionCache.__init__ from session/session-projection-cache/src/index.ts")

checkpointIdentity = None  # port: surface stub (reexport)

checkpointRecord = None  # port: surface stub (reexport)

checkpointRow = None  # port: surface stub (reexport)

projectionCacheDomainSpec = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass
