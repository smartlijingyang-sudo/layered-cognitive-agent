"""Auto-generated surface skeleton for upstream ``client/ui-trajectory/src/client/timeline.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``client/ui-trajectory/src/client/timeline.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TrajectoryTimeRange",
    "TrajectoryTimelineMode",
    "TrajectoryTimelineModel",
    "TrajectoryTimelineSpan",
    "TrajectoryTimelineTurnBoundary",
    "deriveTrajectoryTimeline",
    "formatTimelineOffset",
    "trajectoryTimelineFocusIndexes",
]

TrajectoryTimelineMode: TypeAlias = object  # port: surface stub

def deriveTrajectoryTimeline(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``deriveTrajectoryTimeline``."""
    raise NotImplementedError("port deriveTrajectoryTimeline from client/ui-trajectory/src/client/timeline.ts")

def formatTimelineOffset(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``formatTimelineOffset``."""
    raise NotImplementedError("port formatTimelineOffset from client/ui-trajectory/src/client/timeline.ts")

def trajectoryTimelineFocusIndexes(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``trajectoryTimelineFocusIndexes``."""
    raise NotImplementedError("port trajectoryTimelineFocusIndexes from client/ui-trajectory/src/client/timeline.ts")

class TrajectoryTimeRange(Protocol):
    """Surface stub for upstream interface ``TrajectoryTimeRange``."""
    pass

class TrajectoryTimelineModel(Protocol):
    """Surface stub for upstream interface ``TrajectoryTimelineModel``."""
    pass

class TrajectoryTimelineSpan(Protocol):
    """Surface stub for upstream interface ``TrajectoryTimelineSpan``."""
    pass

class TrajectoryTimelineTurnBoundary(Protocol):
    """Surface stub for upstream interface ``TrajectoryTimelineTurnBoundary``."""
    pass
