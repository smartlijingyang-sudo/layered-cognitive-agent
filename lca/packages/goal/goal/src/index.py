"""Auto-generated surface skeleton for upstream ``goal/goal/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``goal/goal/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "GOAL_CHANGE_VERSION",
    "Config",
    "GoalError",
    "GoalId",
    "GoalService",
    "ResolvedConfig",
    "applyGoalProjection",
    "decodeGoalChange",
    "foldGoal",
    "goalChangeRef",
]

def applyGoalProjection(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyGoalProjection``."""
    raise NotImplementedError("port applyGoalProjection from goal/goal/src/index.ts")

class GoalService:
    """Surface stub for upstream class ``GoalService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port GoalService.__init__ from goal/goal/src/index.ts")

GOAL_CHANGE_VERSION = None  # port: surface stub (reexport)

GoalError = None  # port: surface stub (reexport)

GoalId = None  # port: surface stub (reexport)

decodeGoalChange = None  # port: surface stub (reexport)

foldGoal = None  # port: surface stub (reexport)

goalChangeRef = None  # port: surface stub (reexport)

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class ResolvedConfig(Protocol):
    """Surface stub for upstream interface ``ResolvedConfig``."""
    pass
