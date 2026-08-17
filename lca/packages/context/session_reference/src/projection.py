"""Auto-generated surface skeleton for upstream ``context/session-reference/src/projection.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``context/session-reference/src/projection.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ReferenceRetentionStats",
    "ReferencedSessionData",
    "retainReferencedSession",
]

def retainReferencedSession(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``retainReferencedSession``."""
    raise NotImplementedError("port retainReferencedSession from context/session-reference/src/projection.ts")

class ReferenceRetentionStats(Protocol):
    """Surface stub for upstream interface ``ReferenceRetentionStats``."""
    pass

class ReferencedSessionData(Protocol):
    """Surface stub for upstream interface ``ReferencedSessionData``."""
    pass
