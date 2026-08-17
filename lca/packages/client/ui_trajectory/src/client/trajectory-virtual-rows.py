"""Auto-generated surface skeleton for upstream ``client/ui-trajectory/src/client/trajectory-virtual-rows.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-trajectory/src/client/trajectory-virtual-rows.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TrajectoryVirtualRow",
    "TrajectoryVirtualRowEntry",
    "VirtualizableTrajectoryRecord",
    "groupTrajectoryVirtualRows",
    "trajectoryVirtualRecordKey",
]

def groupTrajectoryVirtualRows(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``groupTrajectoryVirtualRows``."""
    raise NotImplementedError("port groupTrajectoryVirtualRows from client/ui-trajectory/src/client/trajectory-virtual-rows.ts")

def trajectoryVirtualRecordKey(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``trajectoryVirtualRecordKey``."""
    raise NotImplementedError("port trajectoryVirtualRecordKey from client/ui-trajectory/src/client/trajectory-virtual-rows.ts")

class TrajectoryVirtualRow(Protocol):
    """Surface stub for upstream interface ``TrajectoryVirtualRow``."""
    pass

class TrajectoryVirtualRowEntry(Protocol):
    """Surface stub for upstream interface ``TrajectoryVirtualRowEntry``."""
    pass

class VirtualizableTrajectoryRecord(Protocol):
    """Surface stub for upstream interface ``VirtualizableTrajectoryRecord``."""
    pass
