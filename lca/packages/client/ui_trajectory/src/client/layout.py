"""Auto-generated surface skeleton for upstream ``client/ui-trajectory/src/client/layout.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-trajectory/src/client/layout.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TrajectoryGroupModel",
    "TrajectoryLayoutInput",
    "TrajectoryTurnModel",
    "appendTrajectoryPartialLayout",
    "deriveTrajectoryLayout",
]

def appendTrajectoryPartialLayout(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``appendTrajectoryPartialLayout``."""
    raise NotImplementedError("port appendTrajectoryPartialLayout from client/ui-trajectory/src/client/layout.ts")

def deriveTrajectoryLayout(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveTrajectoryLayout``."""
    raise NotImplementedError("port deriveTrajectoryLayout from client/ui-trajectory/src/client/layout.ts")

class TrajectoryGroupModel(Protocol):
    """Surface stub for upstream interface ``TrajectoryGroupModel``."""
    pass

class TrajectoryLayoutInput(Protocol):
    """Surface stub for upstream interface ``TrajectoryLayoutInput``."""
    pass

class TrajectoryTurnModel(Protocol):
    """Surface stub for upstream interface ``TrajectoryTurnModel``."""
    pass
