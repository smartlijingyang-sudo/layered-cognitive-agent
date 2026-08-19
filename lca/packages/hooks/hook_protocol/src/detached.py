"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/detached.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hook-protocol/src/detached.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "DetachedRuns",
    "createDetachedRuns",
]

def createDetachedRuns(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createDetachedRuns``."""
    raise NotImplementedError("port createDetachedRuns from hooks/hook-protocol/src/detached.ts")

class DetachedRuns(Protocol):
    """Surface stub for upstream interface ``DetachedRuns``."""
    pass
