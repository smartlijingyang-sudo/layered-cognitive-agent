"""Auto-generated surface skeleton for upstream ``client/ui-trajectory/src/client/trajectory-record.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-trajectory/src/client/trajectory-record.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AssistantMetricDetail",
    "TrajectoryCellKind",
    "TrajectoryCellProps",
    "TrajectorySourceBlock",
    "formatDurationMillis",
    "formatElapsedSeconds",
    "trajectoryRecordId",
]

TrajectoryCellKind: TypeAlias = object  # port: surface stub

def formatDurationMillis(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatDurationMillis``."""
    raise NotImplementedError("port formatDurationMillis from client/ui-trajectory/src/client/trajectory-record.ts")

def formatElapsedSeconds(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatElapsedSeconds``."""
    raise NotImplementedError("port formatElapsedSeconds from client/ui-trajectory/src/client/trajectory-record.ts")

def trajectoryRecordId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``trajectoryRecordId``."""
    raise NotImplementedError("port trajectoryRecordId from client/ui-trajectory/src/client/trajectory-record.ts")

class AssistantMetricDetail(Protocol):
    """Surface stub for upstream interface ``AssistantMetricDetail``."""
    pass

class TrajectoryCellProps(Protocol):
    """Surface stub for upstream interface ``TrajectoryCellProps``."""
    pass

class TrajectorySourceBlock(Protocol):
    """Surface stub for upstream interface ``TrajectorySourceBlock``."""
    pass
