"""Auto-generated surface skeleton for upstream ``workflow/workflow-worker-thread/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``workflow/workflow-worker-thread/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ChildHandle",
    "ChildPort",
    "ChildResult",
    "ChildStartRequest",
    "WorkerInit",
    "WorkerLimits",
]

class ChildHandle(Protocol):
    """Surface stub for upstream interface ``ChildHandle``."""
    pass

class ChildPort(Protocol):
    """Surface stub for upstream interface ``ChildPort``."""
    pass

class ChildResult(Protocol):
    """Surface stub for upstream interface ``ChildResult``."""
    pass

class ChildStartRequest(Protocol):
    """Surface stub for upstream interface ``ChildStartRequest``."""
    pass

class WorkerInit(Protocol):
    """Surface stub for upstream interface ``WorkerInit``."""
    pass

class WorkerLimits(Protocol):
    """Surface stub for upstream interface ``WorkerLimits``."""
    pass
