"""Auto-generated surface skeleton for upstream ``goal/goal/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``goal/goal/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CreateGoalRequest",
    "CreateGoalResult",
    "EditGoalRequest",
    "GoalActivation",
    "GoalBlockReason",
    "GoalId",
    "GoalPhase",
    "GoalProjection",
    "GoalRef",
    "GoalSnapshot",
    "GoalView",
]

GoalActivation: TypeAlias = object  # port: surface stub

GoalId: TypeAlias = object  # port: surface stub

GoalPhase: TypeAlias = object  # port: surface stub

class CreateGoalRequest(Protocol):
    """Surface stub for upstream interface ``CreateGoalRequest``."""
    pass

class CreateGoalResult(Protocol):
    """Surface stub for upstream interface ``CreateGoalResult``."""
    pass

class EditGoalRequest(Protocol):
    """Surface stub for upstream interface ``EditGoalRequest``."""
    pass

class GoalBlockReason(Protocol):
    """Surface stub for upstream interface ``GoalBlockReason``."""
    pass

class GoalProjection(Protocol):
    """Surface stub for upstream interface ``GoalProjection``."""
    pass

class GoalRef(Protocol):
    """Surface stub for upstream interface ``GoalRef``."""
    pass

class GoalSnapshot(Protocol):
    """Surface stub for upstream interface ``GoalSnapshot``."""
    pass

class GoalView(Protocol):
    """Surface stub for upstream interface ``GoalView``."""
    pass
